#!/usr/bin/env bash
# Tell GitHub to review the next unreviewed Monero PR. One PR per run.
#
# The review runs on GitHub's runners and files an issue, exactly as a manual
# `gh workflow run` does. This script only presses the button, because GitHub's
# own scheduler has never fired for this repo -- see "the schedule" in the
# README.
#
# This is one of two ways to drive the drip. The other is scripts/drip.sh, which
# reviews on this machine and needs no credential but leaves results in
# reviews/ instead of filing issues.
#
#   Run ONE of them, not both. This one skips PRs by looking at issue markers
#   in the repo; drip.sh skips them by looking at reviews/ filenames. Neither
#   sees the other's record, so running both will double-review and
#   double-spend your Claude limits.
#
# CREDENTIAL: a **fine-grained** PAT, this repository only, with exactly one
# permission -- Actions: Read and write. If it leaks, the holder can start this
# workflow. Nothing else: not your code, not other repos, not SSH keys, not org
# settings. This is the whole reason to prefer it over a classic token.
#
#   Create at: https://github.com/settings/personal-access-tokens/new
#     Resource owner ......... xmrack
#     Repository access ...... Only select repositories -> xmrack/monero-review
#     Permissions ............ Repository -> Actions -> Read and write
#     Everything else ........ No access
#     Expiration ............. 90 days
#   The result starts with `github_pat_`. Do NOT use a classic `ghp_` token.
#
# Supply it either way:
#   - GH_TOKEN already in the environment (systemd-creds, pass, gopass) --
#     preferred, nothing lands on disk; or
#   - a file at $TOKEN_FILE, mode 600. Looser modes are refused.
#
# A file is needed rather than `gh auth` because gh's keyring backend wants a
# desktop session, which cron does not have.
#
# Setup:
#   install -m 600 /dev/null ~/.config/monero-review.token
#   $EDITOR ~/.config/monero-review.token     # paste the github_pat_... token
#   ./scripts/dispatch.sh                     # test it by hand first
#   crontab -e                                # then add, with an absolute path:
#     23,53 * * * * /home/jack/Desktop/monero-review/scripts/dispatch.sh >> /tmp/monero-review.log 2>&1
#
# Watch it:  tail -f /tmp/monero-review.log
#            gh run list --repo xmrack/monero-review
# Pause it:  gh variable set REVIEW_PAUSED --body 1 --repo xmrack/monero-review
set -euo pipefail

REPO=${REPO:-xmrack/monero-review}
WORKFLOW=${WORKFLOW:-review.yml}
TOKEN_FILE=${TOKEN_FILE:-$HOME/.config/monero-review.token}

# cron gives you a near-empty PATH.
export PATH="/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin:${PATH:-}"

log() { echo "$(date -Is) $*"; }

if ! command -v gh >/dev/null 2>&1; then
  log "ERROR: gh not on PATH ($PATH)"
  exit 1
fi

# Prefer a token from the environment: then nothing is on disk at all.
token=${GH_TOKEN:-${GITHUB_TOKEN:-}}

if [ -z "$token" ]; then
  if [ ! -r "$TOKEN_FILE" ]; then
    log "ERROR: no token in GH_TOKEN and none readable at $TOKEN_FILE"
    log "       see the setup notes at the top of this script"
    exit 1
  fi
  mode=$(stat -c %a "$TOKEN_FILE" 2>/dev/null || echo unknown)
  case "$mode" in
    600|400) ;;
    *) log "ERROR: $TOKEN_FILE is mode $mode; refusing. chmod 600 it."; exit 1 ;;
  esac
  token=$(tr -d '\r\n' < "$TOKEN_FILE")
fi

if [ -z "$token" ]; then
  log "ERROR: token is empty"
  exit 1
fi

case "$token" in
  ghp_*|gho_*|ghs_*)
    log "WARNING: that looks like a classic PAT, which carries far more access"
    log "         than this needs. Prefer a fine-grained token scoped to $REPO"
    log "         with only Actions: write."
    ;;
esac

# `-f pr=sweep` means "take the next unreviewed PR from the queue". The workflow
# does its own dedup, so a tick with nothing to do is cheap and files nothing.
if GH_TOKEN="$token" gh workflow run "$WORKFLOW" --repo "$REPO" -f pr=sweep 2>&1; then
  log "dispatched sweep to $REPO"
else
  log "ERROR: dispatch failed"
  exit 1
fi
