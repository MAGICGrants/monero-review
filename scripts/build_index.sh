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
find src contrib -type f \
  \( -name '*.c'  -o -name '*.cc'  -o -name '*.cpp' \
  -o -name '*.h'  -o -name '*.hpp' -o -name '*.inl' \) \
  > cscope.files 2>/dev/null || : > cscope.files

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
