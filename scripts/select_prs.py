#!/usr/bin/env python3
"""Pick which upstream PRs to review next.

Prints `prs=<json array>` on stdout for $GITHUB_OUTPUT; diagnostics on stderr.

Selection is a queue, not a recency window:
  - open, non-draft, updated within MAX_AGE_DAYS
  - head SHA not already present in this repo's issue titles (the dedup record)
  - touches something worth reviewing (see WORTHLESS)
  - most recently active first, take BATCH

Doc-only PRs are skipped rather than marked, so they cost one cheap API probe
per tick and become eligible automatically if they later add code.

Env: UPSTREAM, REVIEW_REPO, MAX_AGE_DAYS, BATCH, GH_TOKEN (optional), API
     (optional base URL, for testing).
"""
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

API = os.environ.get("API", "https://api.github.com")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

# A PR whose every changed file matches this has nothing for a security review
# of consensus / memory safety / crypto to act on. Deliberately narrow: build
# files, CI, and anything under src/ or contrib/ stay reviewable, because a
# malicious build or workflow change is a real supply-chain concern.
WORTHLESS = re.compile(
    r"(^docs/"
    r"|^translations/"
    # NB: no bare \.txt$ -- that would swallow CMakeLists.txt and silently
    # skip build-config changes. Fail open on anything not clearly prose.
    r"|\.md$|\.rst$"
    r"|^LICENSE|^COPYING"
    r"|^\.gitignore$|^\.gitattributes$|^\.editorconfig$"
    r"|^\.github/(ISSUE_TEMPLATE|PULL_REQUEST_TEMPLATE)"
    r")",
    re.IGNORECASE,
)

# Stop probing after this many candidates in one tick, so a queue full of
# doc-only PRs can't turn into an unbounded API sweep.
MAX_PROBES = 20


def get(path, params=None):
    url = f"{API}{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "monero-review",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def reviewed_shas(repo):
    """Every 12-char SHA recorded in this repo's issue titles."""
    seen = set()
    for page in range(1, 11):
        try:
            issues = get(f"/repos/{repo}/issues",
                         {"state": "all", "per_page": 100, "page": page})
        except urllib.error.HTTPError as exc:
            print(f"warn: issue listing failed ({exc.code}); "
                  "assuming nothing reviewed", file=sys.stderr)
            return seen
        if not issues:
            break
        for issue in issues:
            seen.update(re.findall(r"\b[0-9a-f]{12}\b", issue.get("title", "")))
        if len(issues) < 100:
            break
    return seen


def worth_reviewing(upstream, number):
    """False only if every changed file is documentation-ish."""
    try:
        files = get(f"/repos/{upstream}/pulls/{number}/files", {"per_page": 100})
    except urllib.error.HTTPError as exc:
        # Fail open: an API hiccup should not silently drop a PR from review.
        print(f"warn: file listing for #{number} failed ({exc.code}); "
              "reviewing anyway", file=sys.stderr)
        return True, []
    names = [f["filename"] for f in files]
    if not names:
        return False, names
    return (not all(WORTHLESS.search(n) for n in names)), names


def main():
    upstream = os.environ["UPSTREAM"]
    repo = os.environ["REVIEW_REPO"]
    batch = int(os.environ.get("BATCH", "1"))
    max_age = int(os.environ.get("MAX_AGE_DAYS", "1"))

    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=max_age)).strftime("%Y-%m-%dT%H:%M:%SZ")

    prs = get(f"/repos/{upstream}/pulls", {
        "state": "open", "per_page": 100,
        "sort": "updated", "direction": "desc",
    })
    done = reviewed_shas(repo)

    queue = [p for p in prs
             if not p["draft"]
             and p["updated_at"] > cutoff
             and p["head"]["sha"][:12] not in done]
    queue.sort(key=lambda p: p["updated_at"], reverse=True)
    print(f"{len(queue)} unreviewed PR(s) updated since {cutoff}",
          file=sys.stderr)

    picked, probes = [], 0
    for pr in queue:
        if len(picked) >= batch or probes >= MAX_PROBES:
            break
        probes += 1
        ok, names = worth_reviewing(upstream, pr["number"])
        if ok:
            picked.append(str(pr["number"]))
            print(f"  take #{pr['number']} ({len(names)} file(s))",
                  file=sys.stderr)
        else:
            print(f"  skip #{pr['number']}: no reviewable code "
                  f"({', '.join(names[:4])})", file=sys.stderr)

    print("prs=" + json.dumps(picked))


if __name__ == "__main__":
    main()
