#!/usr/bin/env python3
"""Append a one-line run footer to review.md.

The claude-code-action `execution_file` schema is not documented, so this
parses defensively: it walks whatever JSON it is given looking for a record
carrying cost/usage fields, and degrades to wall-clock only if it finds
nothing. It must never fail the job -- any error just means a shorter footer.

Env:
  EXEC_FILE   path to the execution log (action output, or `claude
              --output-format json` stdout). Optional. Accepts a
              comma-separated list -- the review and refutation passes are
              separate invocations and their metrics are summed.
  REVIEW_MD   review file to append to. Default: review.md
  T0          unix timestamp taken before the review started. Optional.
  MODEL       model name to display. Optional.
  RUN_URL     link to the CI run. Optional.
"""
import json
import os
import sys
import time

USAGE_KEYS = ("input_tokens", "output_tokens",
              "cache_read_input_tokens", "cache_creation_input_tokens")


def find_result(node, depth=0):
    """Deepest-first search for a dict carrying run metrics."""
    if depth > 6:
        return None
    if isinstance(node, dict):
        if any(k in node for k in ("total_cost_usd", "duration_ms", "usage")):
            return node
        for key in ("result", "data", "summary"):
            if key in node:
                hit = find_result(node[key], depth + 1)
                if hit:
                    return hit
        return None
    if isinstance(node, list):
        # stream-json: the terminal `result` event is last
        for item in reversed(node):
            hit = find_result(item, depth + 1)
            if hit:
                return hit
    return None


def load(path):
    with open(path) as fh:
        text = fh.read().strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # JSONL fallback
        events = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return events or None


def merge(results):
    """Sum metrics across passes (review, then refutation)."""
    if len(results) == 1:
        return results[0]
    total = {"usage": {}, "passes": len(results)}
    for key in ("duration_ms", "num_turns", "total_cost_usd"):
        vals = [r.get(key) for r in results if isinstance(r.get(key), (int, float))]
        if vals:
            total[key] = sum(vals)
    for key in USAGE_KEYS:
        vals = [(r.get("usage") or {}).get(key) for r in results]
        vals = [v for v in vals if isinstance(v, (int, float))]
        if vals:
            total["usage"][key] = sum(vals)
    return total


def human(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def dur(seconds):
    seconds = int(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"
    if seconds >= 60:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds}s"


def main():
    review = os.environ.get("REVIEW_MD", "review.md")
    if not os.path.exists(review) or os.path.getsize(review) == 0:
        return

    bits = []
    model = os.environ.get("MODEL")
    if model:
        bits.append(f"`{model}`")

    t0 = os.environ.get("T0")
    if t0:
        try:
            bits.append(f"{dur(time.time() - float(t0))} wall")
        except ValueError:
            pass

    # De-duplicate: claude-code-action wrote both passes to one path, so an
    # unguarded list could contain the same file twice and merge() would sum a
    # pass with itself -- inflating turns, duration and cost on every two-pass
    # footer. The workflow now snapshots pass 1, but a footer that silently
    # doubles its numbers is bad enough to guard in both places.
    seen = set()
    paths = []
    for raw in os.environ.get("EXEC_FILE", "").split(","):
        path = raw.strip()
        if not path:
            continue
        key = os.path.realpath(path)
        if key in seen:
            print(f"telemetry: ignoring duplicate execution log {path}",
                  file=sys.stderr)
            continue
        seen.add(key)
        paths.append(path)
    results = []
    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            found = find_result(load(path))
        except Exception as exc:                      # noqa: BLE001
            print(f"telemetry: could not parse {path}: {exc}", file=sys.stderr)
            continue
        if found:
            results.append(found)

    result = merge(results) if results else None

    if result:
        ms = result.get("duration_ms")
        if isinstance(ms, (int, float)):
            bits.append(f"{dur(ms / 1000)} model")

        turns = result.get("num_turns")
        if isinstance(turns, int):
            passes = result.get("passes")
            bits.append(f"{turns} turns" + (f" over {passes} passes" if passes else ""))

        usage = result.get("usage") or {}
        if isinstance(usage, dict) and any(k in usage for k in USAGE_KEYS):
            got = {k: usage.get(k) or 0 for k in USAGE_KEYS}
            inp = got["input_tokens"] + got["cache_read_input_tokens"] \
                + got["cache_creation_input_tokens"]
            cached = got["cache_read_input_tokens"]
            piece = f"{human(inp)} in"
            if cached:
                piece += f" ({human(cached)} cached)"
            piece += f" / {human(got['output_tokens'])} out"
            bits.append(piece)

        cost = result.get("total_cost_usd")
        if isinstance(cost, (int, float)) and cost > 0:
            # Runs bill against a Claude subscription, not the API. This is the
            # API-rate equivalent -- useful for comparing PRs, not a charge.
            bits.append(f"~${cost:.2f} at API rates")
    elif paths:
        bits.append("token stats unavailable")

    run_url = os.environ.get("RUN_URL")
    if run_url:
        bits.append(f"[run]({run_url})")

    if not bits:
        return

    with open(review, "a") as fh:
        fh.write("\n\n---\n<sub>" + " · ".join(bits) + "</sub>\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:                          # noqa: BLE001
        print(f"telemetry: {exc}", file=sys.stderr)
    sys.exit(0)
