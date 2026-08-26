#!/usr/bin/env bash
# Review an upstream Monero PR locally, using the same skill the workflow uses.
# No GitHub Actions, no secrets, no runner -- just your authenticated claude CLI.
#
#   ./review-local.sh 9876              # review PR 9876 with Opus
#   ./review-local.sh 9876 claude-sonnet-5
#
# Findings land in reviews/pr-<n>-<sha>.md
set -euo pipefail

PR=${1:?usage: review-local.sh <upstream-pr-number> [model]}
MODEL=${2:-claude-opus-5}
UPSTREAM=${UPSTREAM:-monero-project/monero}

[[ "$PR" =~ ^[0-9]+$ ]] || { echo "PR must be a number" >&2; exit 1; }

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CACHE=${CACHE:-$HOME/.cache/monero-review/src}

# Blobless partial clone, cached between runs so only the first is slow.
if [ ! -d "$CACHE/.git" ]; then
  echo "==> first run: cloning $UPSTREAM (blobless, ~1-2 min)"
  git clone --filter=blob:none --no-tags --single-branch --branch master \
    "https://github.com/$UPSTREAM.git" "$CACHE"
fi

echo "==> fetching PR $PR"
git -C "$CACHE" fetch --filter=blob:none --quiet origin \
  "+refs/heads/master:refs/remotes/origin/master" \
  "+refs/pull/$PR/head:refs/heads/pr-$PR"
git -C "$CACHE" checkout --quiet --force "pr-$PR"

SHA=$(git -C "$CACHE" rev-parse --short HEAD)
echo "==> PR $PR is at $SHA"

# The skill lives here, not in the Monero tree.
rm -rf "$CACHE/.claude"
cp -r "$HERE/.claude" "$CACHE/.claude"

if command -v jq >/dev/null 2>&1; then
  curl -fsSL "https://api.github.com/repos/$UPSTREAM/pulls/$PR" \
    | jq -r '"# \(.title)\n\n\(.body // "(no description)")"' > "$CACHE/PR_CONTEXT.md"
else
  echo "(install jq for PR title/description context)" > "$CACHE/PR_CONTEXT.md"
fi

# Symbol index for precise cross-reference. Skipped silently if ctags/cscope
# are absent -- `sudo apt install universal-ctags cscope` to enable.
bash "$HERE/scripts/build_index.sh" "$CACHE"

TOOLS="Read,Grep,Glob,Write,Bash(git diff:*),Bash(git log:*),Bash(git show:*),Bash(git blame:*),Bash(git merge-base:*),Bash(readtags:*),Bash(cscope:*)"

rm -f "$CACHE/review.md" "$CACHE/exec.json" "$CACHE/exec-refute.json"
echo "==> reviewing with $MODEL"
T0=$(date +%s)
( cd "$CACHE" && claude -p "/monero-security-review" \
    --model "$MODEL" --output-format json --allowedTools "$TOOLS" > exec.json )

if [ ! -s "$CACHE/review.md" ]; then
  echo "!! no review.md produced" >&2
  exit 1
fi

# Adversarial second pass, only if the first found something to attack.
EXEC_FILES="$CACHE/exec.json"
if grep -q '^## Findings' "$CACHE/review.md"; then
  echo "==> findings present, verifying"
  ( cd "$CACHE" && claude -p "/monero-review-refute" \
      --model "$MODEL" --output-format json --allowedTools "$TOOLS" \
      > exec-refute.json )
  EXEC_FILES="$EXEC_FILES,$CACHE/exec-refute.json"
else
  echo "==> no findings, skipping verification"
fi

# Same footer the workflow appends: model, wall clock, turns, tokens, cost.
EXEC_FILE="$EXEC_FILES" REVIEW_MD="$CACHE/review.md" T0="$T0" MODEL="$MODEL" \
  python3 "$HERE/scripts/telemetry.py"

mkdir -p "$HERE/reviews"
OUT="$HERE/reviews/pr-$PR-$SHA.md"
cp "$CACHE/review.md" "$OUT"
echo "==> $OUT"
