# monero-review

Automated security review of monero-project/monero pull requests.

It pulls down a PR's head commit, has Claude read the diff against a
Monero-specific review skill, and reports what it finds. A second pass then
tries to knock down every finding before anything is reported, since most
first-pass findings turn out to be wrong. Nothing from the PR is ever built or
executed, and Claude has no network or GitHub access — it just writes a file,
and the script around it decides what to do with that.

## Review one PR

Locally — no secrets, no runner, results in `reviews/`:

```bash
./review-local.sh 11155
```

Or on GitHub Actions, which files the result as an issue here:

```bash
gh workflow run review.yml --repo xmrack/monero-review -f pr=11155
```

## Review new PRs automatically

Each tick reviews one PR and files what it finds as an issue here. Only one
review runs at a time, repo-wide.

**Drive it from something other than GitHub's scheduler.** Either dispatch the
workflow on a timer from a machine that stays up, which files results as issues:

```
23,53 * * * * cd /home/jack/Desktop/monero-review && gh workflow run review.yml -f pr=sweep >> /tmp/monero-review.log 2>&1
```

...or run the whole review locally with `scripts/drip.sh`, which needs no
credential but leaves results in `reviews/` instead of filing issues:

```
23,53 * * * * /home/jack/Desktop/monero-review/scripts/drip.sh >> /tmp/monero-review.log 2>&1
```

Pick one. The two dedup differently — `drip.sh` skips PRs by looking at
`reviews/` filenames, CI skips them by looking at issue markers, and neither
sees the other's record — so running both will double-review PRs and
double-spend the subscription.

Pause either with:

```bash
gh variable set REVIEW_PAUSED --body 1 --repo xmrack/monero-review
```

`--body 0` resumes. Reviewing a specific PR by number still works while paused.

### The schedule

`review.yml` still carries a `schedule:` block, at `23,53`. It is a free backup
in case GitHub's scheduler starts working, not the clock.

It has never fired. Measured 2026-08-26/27: four different crons were live on
the default branch — `*/30`, `17 2,6,10,14,18,22`, `7,27,47`, and `*/5` — and
across every one of them the repo recorded **zero** runs with
`event=schedule`, while `workflow_dispatch` succeeded 4/4 in the same window.
A `*/30` cron sat on `main` for at least 4h20m without firing.

It is not congestion, and moving the minute does not help — every
minute-of-hour has been tried. The evidence points at the workflow's cron
registration: the workflow record was ingested once, at 18:20:00Z, from the one
commit where `schedule:` was still commented out, and `updated_at` stayed frozen
at that timestamp through fourteen later edits to the file, four of which added
a live cron. So the scheduler holds a registration for a workflow it believes
has no cron, while the dispatch path reads the live file correctly.

Renaming the file from `security-review.yml` to `review.yml` was the fix for
that: a new path forces GitHub to create a new workflow record and ingest the
cron. `cron-canary.yml` is the control — it has no trigger but `schedule:`, so
any run it produces is provably schedule-fired. Check both:

```bash
gh run list --repo xmrack/monero-review --workflow cron-canary.yml
gh api "repos/xmrack/monero-review/actions/runs?event=schedule" --jq .total_count
```

If the canary fires and `review.yml` does not, that workflow's registration is
stuck again — rename it. If neither fires within an hour, schedules are
suppressed repo- or account-wide and renaming will not help. Delete the canary
once the question is settled.

Do not test this by disabling and re-enabling the workflow: re-enabling
re-registers the cron, which destroys the evidence that distinguishes "never
registered" from "was disabled". Read `state`, never write it.

## Where things are

`.claude/skills/monero-security-review/SKILL.md` is the review itself — edit
that if the output isn't sharp enough. `scripts/select_prs.py` decides which PR
is next and skips ones already reviewed.
