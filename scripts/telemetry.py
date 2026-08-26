#!/usr/bin/env python3
"""Append a one-line run footer to review.md.

The claude-code-action `execution_file` schema is not documented, so this
parses defensively: it walks whatever JSON it is given looking for a record
carrying cost/usage fields, and degrades to wall-clock only if it finds
nothing. It must never fail the job -- any error just means a shorter footer.

Env:
  EXEC_FILE   path to the execution log (action output, or `claude
              --output-format json` stdout). Optional.
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

    exec_file = os.environ.get("EXEC_FILE")
    result = None
    if exec_file and os.path.exists(exec_file):
        try:
            result = find_result(load(exec_file))
        except Exception as exc:                      # noqa: BLE001
            print(f"telemetry: could not parse {exec_file}: {exc}",
                  file=sys.stderr)

    if result:
        ms = result.get("duration_ms")
        if isinstance(ms, (int, float)):
            bits.append(f"{dur(ms / 1000)} model")

        turns = result.get("num_turns")
        if isinstance(turns, int):
            bits.append(f"{turns} turns")

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
    elif exec_file:
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
