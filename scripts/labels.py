#!/usr/bin/env python3
"""Print the severity labels a review warrants, one per line, highest first.

    python3 scripts/labels.py [review.md]

Only findings that SURVIVED verification count. Refuted ones stay in the report
on purpose -- so a reader can see what was considered and dismissed -- but they
must not label the issue. Two things are therefore ignored:

  - everything from a "## Refuted ..." heading onward
  - any finding heading whose own text says REFUTED

Prints nothing when there are no surviving findings, which is the common case.
"""
import re
import sys

# Highest first, so the caller can take the first line as the headline severity.
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

HEADING = re.compile(
    r"^###\s*\[\s*(CRITICAL|HIGH|MEDIUM|LOW)\b([^\]]*)\]\s*(.*)$",
    re.MULTILINE | re.IGNORECASE,
)
REFUTED_SECTION = re.compile(r"^##\s+Refuted\b", re.MULTILINE | re.IGNORECASE)


def severities(text):
    cut = REFUTED_SECTION.search(text)
    if cut:
        text = text[:cut.start()]

    found = set()
    for match in HEADING.finditer(text):
        # The bracket may hold "SEVERITY / CONFIDENCE"; the tail is the title.
        tail = (match.group(2) or "") + (match.group(3) or "")
        if re.search(r"refuted", tail, re.IGNORECASE):
            continue
        found.add(match.group(1).upper())
    return [s for s in SEVERITIES if s in found]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "review.md"
    try:
        with open(path, errors="replace") as fh:
            text = fh.read()
    except OSError:
        return
    for sev in severities(text):
        print(sev.lower())


if __name__ == "__main__":
    main()
