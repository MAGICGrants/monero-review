#!/usr/bin/env bash
# Build a symbol index so the review can answer "who calls this" precisely
# instead of guessing from grep. ctags and cscope PARSE source text; they do
# not configure, compile, or execute anything from the PR.
#
# Degrades silently: if the tools are absent the review falls back to grep.
set -euo pipefail

cd "${1:-.}"

have() { command -v "$1" >/dev/null 2>&1; }

if ! have ctags && ! have cscope; then
  echo "index: ctags/cscope not installed -- skipping, review falls back to grep" >&2
  exit 0
fi

# Security surface only. tests/ and utils/ are excluded to keep the index
# small and the caller lists free of harness noise.
#
# Collect the directories that exist first: `find a b` where b is missing exits
# non-zero *after* writing a's results, and a `|| :` fallback would then discard
# them. UPSTREAM is configurable, so don't assume Monero's layout.
dirs=""
for d in src contrib; do
  [ -d "$d" ] && dirs="$dirs $d"
done
if [ -z "$dirs" ]; then
  echo "index: no src/ or contrib/ here, skipping" >&2
  exit 0
fi

# shellcheck disable=SC2086  # word splitting on $dirs is intended
find $dirs -type f \
  \( -name '*.c'  -o -name '*.cc'  -o -name '*.cpp' \
  -o -name '*.h'  -o -name '*.hpp' -o -name '*.inl' \) \
  > cscope.files 2>/dev/null || true

count=$(wc -l < cscope.files | tr -d ' ')
if [ "$count" = "0" ]; then
  echo "index: no source files found, skipping" >&2
  exit 0
fi
echo "index: ${count} source files" >&2

if have ctags; then
  if ctags --languages=C,C++ --fields=+ne --extras=+q \
       -L cscope.files -f tags 2>/dev/null; then
    echo "index: tags built ($(wc -l < tags | tr -d ' ') entries)" >&2
  else
    echo "index: ctags failed, continuing without it" >&2
  fi
fi

if have cscope; then
  if cscope -b -q -k -i cscope.files 2>/dev/null; then
    echo "index: cscope database built" >&2
  else
    echo "index: cscope failed, continuing without it" >&2
  fi
fi
