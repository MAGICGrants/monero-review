#!/usr/bin/env bash
# Drive one sweep tick from a machine whose cron actually runs.
#
# GitHub's scheduler is best-effort on public repos and has not fired for this
# account; this is the reliable path. Safe to run alongside the workflow's own
# `schedule:` -- the workflow's concurrency group collapses overlapping runs and
# dedup is keyed on head SHA, so a double trigger costs nothing.
#
# Setup (once):
#   printf '%s\n' 'ghp_yourtoken' > ~/.config/monero-review.token
#   chmod 600 ~/.config/monero-review.token
#   crontab -e   # then add, with an absolute path:
#     */30 * * * * /home/jack/Desktop/monero-review/scripts/drip.sh >> /tmp/monero-review-drip.log 2>&1
#
# The token needs `repo` scope. A file is used rather than `gh auth` because
# gh's keyring backend needs a desktop session, which cron does not have.
set -euo pipefail

REPO=${REPO:-xmrack/monero-review}
TOKEN_FILE=${TOKEN_FILE:-$HOME/.config/monero-review.token}

# cron gives you a near-empty PATH.
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"

log() { echo "$(date -Is) $*"; }

if ! command -v gh >/dev/null 2>&1; then
  log "ERROR: gh not found on PATH ($PATH)"
  exit 1
fi

if [ ! -r "$TOKEN_FILE" ]; then
  log "ERROR: no readable token at $TOKEN_FILE"
  exit 1
fi

if [ "$(stat -c %a "$TOKEN_FILE" 2>/dev/null || echo 600)" != "600" ]; then
  log "WARNING: $TOKEN_FILE is not mode 600"
fi

token=$(tr -d '\r\n' < "$TOKEN_FILE")
if [ -z "$token" ]; then
  log "ERROR: $TOKEN_FILE is empty"
  exit 1
fi

if GH_TOKEN="$token" gh workflow run security-review.yml \
     --repo "$REPO" -f pr=sweep 2>&1; then
  log "dispatched sweep to $REPO"
else
  log "ERROR: dispatch failed"
  exit 1
fi
