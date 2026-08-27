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
import collections
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

# Failed attempts at the same head SHA before the queue moves on. 2 gives a
# transient failure one retry without letting a reliably-failing PR block
# everything behind it.
MAX_ATTEMPTS = 2

# Pages of open PRs to consider, 100 each. Upstream runs ~300 open, so one page
# would hide the backlog behind the most-recently-updated 100.
MAX_PR_PAGES = 5


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


def review_state(repo):
    """Read this repo's issue titles as the record of what has been attempted.

    Returns (done, failed): SHAs with a completed review, and a count of
    failed attempts per SHA. A SHA is retried after a failure -- but only
    MAX_ATTEMPTS times, or a PR that reliably fails would be the newest
    unreviewed item on every tick and block the queue forever.
    """
    done, failed = set(), collections.Counter()
    for page in range(1, 11):
        try:
            issues = get(f"/repos/{repo}/issues",
                         {"state": "all", "per_page": 100, "page": page})
        except urllib.error.HTTPError as exc:
            print(f"warn: issue listing failed ({exc.code}); "
                  "assuming nothing reviewed", file=sys.stderr)
            return done, failed
        if not issues:
            break
        for issue in issues:
            title = issue.get("title", "")
            shas = re.findall(r"\b[0-9a-f]{12}\b", title)
            if title.startswith("Review FAILED:"):
                failed.update(shas)
            else:
                done.update(shas)
        if len(issues) < 100:
            break
    return done, failed


def local_reviewed(dirpath):
    """SHAs already reviewed locally.

    review-local.sh names its output reviews/pr-<number>-<sha12>.md, so the
    directory listing *is* the local dedup record -- no extra state file.
    """
    seen = set()
    if not dirpath or not os.path.isdir(dirpath):
        return seen
    for name in os.listdir(dirpath):
        seen.update(re.findall(r"\b[0-9a-f]{12}\b", name))
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
    # A full page means there are more files we cannot see. Fail open rather
    # than judge a large PR on a truncated list.
    if len(names) >= 100:
        return True, names
    return (not all(WORTHLESS.search(n) for n in names)), names


def main():
    upstream = os.environ["UPSTREAM"]
    repo = os.environ["REVIEW_REPO"]
    batch = int(os.environ.get("BATCH", "1"))
    max_age = int(os.environ.get("MAX_AGE_DAYS", "1"))

    # MAX_AGE_DAYS=0 means no age limit: every open PR is eligible, so the queue
    # chips through the backlog once recent work is done. Sorting is still
    # most-recently-active first, so fresh PRs keep priority and old ones are
    # only reached when nothing newer is unreviewed.
    if max_age <= 0:
        cutoff = ""
    else:
        cutoff = (datetime.datetime.now(datetime.timezone.utc)
                  - datetime.timedelta(days=max_age)
                  ).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Paginate: upstream has far more than one page of open PRs, and a single
    # page silently caps the queue at the 100 most-recently-updated -- which
    # makes the backlog permanently invisible however wide MAX_AGE_DAYS is.
    prs = []
    for page in range(1, MAX_PR_PAGES + 1):
        batch_of_prs = get(f"/repos/{upstream}/pulls", {
            "state": "open", "per_page": 100, "page": page,
            "sort": "updated", "direction": "desc",
        })
        if not batch_of_prs:
            break
        prs.extend(batch_of_prs)
        if len(batch_of_prs) < 100:
            break
    done, failed = review_state(repo)

    # Local runs record themselves as filenames; count those as done too, so a
    # locally driven drip and the CI workflow don't duplicate each other's work.
    local = local_reviewed(os.environ.get("REVIEWS_DIR"))
    if local:
        print(f"{len(local)} SHA(s) already reviewed locally", file=sys.stderr)
        done |= local

    def pending(p):
        sha = p["head"]["sha"][:12]
        if sha in done:
            return False
        if failed[sha] >= MAX_ATTEMPTS:
            print(f"  give up on #{p['number']}: {failed[sha]} failed attempts "
                  f"at {sha}", file=sys.stderr)
            return False
        return True

    queue = [p for p in prs
             if not p["draft"]
             and p["updated_at"] > cutoff
             and pending(p)]
    queue.sort(key=lambda p: p["updated_at"], reverse=True)
    scope = f"updated since {cutoff}" if cutoff else "of any age"
    print(f"{len(queue)} unreviewed PR(s) {scope}, out of {len(prs)} open",
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
