#!/usr/bin/env bash
# Drive one sweep tick from a machine whose cron actually runs.
#
# GitHub's scheduler is best-effort on public repos and has not fired for this
# account; this is the reliable path. Safe to run alongside the workflow's own
# `schedule:` -- the workflow's concurrency group collapses overlapping runs and
# dedup is keyed on head SHA, so a double trigger costs nothing.
#
# CREDENTIAL: use a **fine-grained** PAT, scoped to this repository only, with
# exactly one permission: Actions -> Read and write. Nothing else. Then the
# worst case if the token leaks is that someone can trigger this workflow.
#
#   DO NOT reuse a classic PAT. A classic token with `repo` (let alone
#   `admin:org` or `admin:public_key`) on disk means anyone who reads the file
#   can rewrite your repositories, add SSH keys to your account, or change org
#   settings. That is a wildly disproportionate blast radius for "start a job".
#
# Supply it either way:
#   - GH_TOKEN already in the environment (systemd-creds, pass, a secret
#     manager) -- preferred, nothing lands on disk; or
#   - a file at $TOKEN_FILE, mode 600. This script refuses looser modes.
#
# A file is needed rather than `gh auth` because gh's keyring backend wants a
# desktop session, which cron does not have.
#
# Setup:
#   crontab -e   # add, with an absolute path:
#     */30 * * * * /home/jack/Desktop/monero-review/scripts/drip.sh >> /tmp/monero-review-drip.log 2>&1
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

# Prefer a token injected into the environment -- then nothing is on disk.
token=${GH_TOKEN:-${GITHUB_TOKEN:-}}

if [ -z "$token" ]; then
  if [ ! -r "$TOKEN_FILE" ]; then
    log "ERROR: no token in GH_TOKEN and none readable at $TOKEN_FILE"
    exit 1
  fi
  mode=$(stat -c %a "$TOKEN_FILE" 2>/dev/null || echo unknown)
  if [ "$mode" != "600" ] && [ "$mode" != "400" ]; then
    log "ERROR: $TOKEN_FILE is mode $mode; refusing. chmod 600 it."
    exit 1
  fi
  token=$(tr -d '\r\n' < "$TOKEN_FILE")
fi

if [ -z "$token" ]; then
  log "ERROR: token is empty"
  exit 1
fi

case "$token" in
  ghp_*|gho_*)
    log "WARNING: that looks like a classic PAT. Prefer a fine-grained token"
    log "         scoped to $REPO with only Actions: write."
    ;;
esac

if GH_TOKEN="$token" gh workflow run security-review.yml \
     --repo "$REPO" -f pr=sweep 2>&1; then
  log "dispatched sweep to $REPO"
else
  log "ERROR: dispatch failed"
  exit 1
fi
