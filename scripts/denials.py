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
import re
import sys
import collections

KEYS = ("permission_denials", "permissionDenials")

# Why a call was refused, so denial review is something the harness does on
# every run rather than something a human does by pasting lists into a chat.
#
# Every shape below was observed in a real run and each has a documented
# alternative in the skills. An UNCLASSIFIED denial is therefore the
# interesting one: it means a NEW cause has appeared and the skills do not yet
# answer it. That is the line worth reading.
CAUSES = (
    # (label, pattern, the answer the skills already give)
    ("rc-echo",      r'echo\s+"?rc\d*=\$\?',
     "the tool result already reports success/failure"),
    ("chain",        r';|&&|\bfor\b[^;]*\bdo\b',
     "one command takes several args: git log --no-walk <sha> <sha>"),
    ("redirect",     r'(?<!2)>\s*[^&\s]',
     "use the Write tool"),
    ("substitution", r'\$\(',
     "resolve it in a separate call"),
    ("outside-tree", r'(^|\s)(/usr/|/etc/|/opt/)|find\s+/\s',
     "/usr/include/boost/X -> deps-include/boost/X"),
    ("git -C",       r'\bgit\s+-C\b',
     "PR_SUBMODULES.md already holds the submodule range"),
)


def classify(cmd):
    """All causes matching one refused command, most specific first."""
    hits = [name for name, pat, _ in CAUSES if re.search(pat, cmd)]
    # rc-echo implies a chain; report the specific reason, not both.
    if "rc-echo" in hits and "chain" in hits:
        hits.remove("chain")
    return hits or ["UNCLASSIFIED"]


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
    # De-duplicate by real path: both passes' logs were written to one path
    # for a while, and counting that file twice would report 24 refused calls
    # where there were 12. The genuine doubling -- a blocked command retried
    # with the sandbox disabled -- is kept, since that is real behaviour worth
    # seeing.
    seen = set()
    paths = []
    for raw in os.environ.get("EXEC_FILE", "").split(","):
        path = raw.strip()
        if not path or not os.path.exists(path):
            continue
        key = os.path.realpath(path)
        if key not in seen:
            seen.add(key)
            paths.append(path)
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
    causes = collections.Counter()
    for (tool, what), n in seen.most_common():
        hits = classify(what)
        causes.update({h: n for h in hits})
        print(f"  x{n} [{tool}] {what}")
        print(f"      cause: {', '.join(hits)}")

    print("denial causes: "
          + ", ".join(f"{c}={n}" for c, n in causes.most_common()))
    answers = {name: fix for name, _, fix in CAUSES}
    for c, _ in causes.most_common():
        if c in answers:
            print(f"  {c}: {answers[c]}")
    if "UNCLASSIFIED" in causes:
        print("  UNCLASSIFIED: a refusal shape the skills do not yet answer -- "
              "worth reading the command above and adding guidance.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:                              # noqa: BLE001
        print(f"denials: {exc}", file=sys.stderr)
    sys.exit(0)
