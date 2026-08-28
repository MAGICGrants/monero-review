#!/usr/bin/env python3
"""Print the tool calls a run had refused, from an execution log.

    EXEC_FILE=<path[,path]> python3 scripts/denials.py

The job log reports only `permission_denials_count`. That number is not
actionable: two runs of the same PR with the same allowlist showed 0 denials
outside Actions and 24 inside it, and without the list there is no way to tell
which calls differ. The array lives in the execution file, so surface it where
a reader of the log can see it.

Parses defensively and never fails the job -- the schema is not documented, and
a missing list is worth a note, not a red run.
"""
import json
import os
import sys
import collections

KEYS = ("permission_denials", "permissionDenials")


def walk(node, depth=0):
    """Yield every permission-denial list found anywhere in the structure."""
    if depth > 8:
        return
    if isinstance(node, dict):
        for k in KEYS:
            if isinstance(node.get(k), list):
                yield node[k]
        for v in node.values():
            yield from walk(v, depth + 1)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v, depth + 1)


def load(path):
    with open(path) as fh:
        text = fh.read().strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        events = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return events or None


def describe(entry):
    """One line for a denied call: the command, or the path, or the raw input."""
    if not isinstance(entry, dict):
        return "Bash", str(entry)[:160]
    tool = entry.get("tool_name") or entry.get("toolName") or "?"
    ti = entry.get("tool_input") or entry.get("toolInput") or {}
    if isinstance(ti, dict):
        what = ti.get("command") or ti.get("file_path") or json.dumps(ti)
        if ti.get("dangerouslyDisableSandbox"):
            what = f"{what}   [sandbox-disabled retry]"
    else:
        what = str(ti)
    return tool, str(what)[:220]


def main():
    paths = [p.strip() for p in os.environ.get("EXEC_FILE", "").split(",")
             if p.strip() and os.path.exists(p.strip())]
    if not paths:
        return
    seen = collections.Counter()
    total = 0
    for path in paths:
        try:
            data = load(path)
        except Exception as exc:                          # noqa: BLE001
            print(f"denials: could not read {path}: {exc}", file=sys.stderr)
            continue
        for lst in walk(data):
            for entry in lst:
                total += 1
                seen[describe(entry)] += 1
    if not total:
        print("denials: none recorded")
        return
    print(f"denials: {total} refused tool call(s), {len(seen)} distinct:")
    for (tool, what), n in seen.most_common():
        print(f"  x{n} [{tool}] {what}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:                              # noqa: BLE001
        print(f"denials: {exc}", file=sys.stderr)
    sys.exit(0)
