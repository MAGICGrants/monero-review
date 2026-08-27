#!/usr/bin/env bash
# Review the next unreviewed Monero PR on this machine. One PR per run.
#
# No GitHub credential: the claude CLI is already authenticated, and picking
# which PR to review only reads public data. Results land in reviews/.
#
# This is the FALLBACK. The workflow has its own schedule: and files results as
# issues; use this only if GitHub's scheduler turns out not to fire (an earlier
# every-30-minutes schedule here never did). Results stay local.
#
# Setup:
#   crontab -e   # add, with absolute paths:
#     */30 * * * * /home/jack/Desktop/monero-review/scripts/drip.sh >> /tmp/monero-review.log 2>&1
#
# Check it is working:
#   tail /tmp/monero-review.log
#   ls ~/Desktop/monero-review/reviews/
set -euo pipefail

# cron gives you a near-empty PATH.
export PATH="/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin:${PATH:-}"

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

log() { echo "$(date -Is) $*"; }

if ! command -v claude >/dev/null 2>&1; then
  log "ERROR: claude not on PATH ($PATH)"
  exit 1
fi

# Ask the queue for one PR. Dedup counts both this repo's issues (public read,
# no token) and reviews/ filenames from previous local runs.
picked=$(
  UPSTREAM=${UPSTREAM:-monero-project/monero} \
  REVIEW_REPO=${REVIEW_REPO:-xmrack/monero-review} \
  REVIEWS_DIR="$HERE/reviews" \
  MAX_AGE_DAYS=${MAX_AGE_DAYS:-1} \
  BATCH=1 \
  python3 "$HERE/scripts/select_prs.py" | sed -n 's/^prs=//p'
)

pr=$(printf '%s' "$picked" | tr -cd '0-9')
if [ -z "$pr" ]; then
  log "nothing to review"
  exit 0
fi

log "reviewing PR $pr"
if "$HERE/review-local.sh" "$pr" "${MODEL:-claude-sonnet-5}"; then
  log "done: PR $pr"
else
  log "ERROR: review of PR $pr failed"
  exit 1
fi
