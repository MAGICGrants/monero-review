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
gh workflow run security-review.yml --repo xmrack/monero-review -f pr=11155
```

## Review new PRs automatically

The workflow runs itself six times a day — 02:17, 06:17, 10:17, 14:17, 18:17
and 22:17 UTC — reviewing up to two PRs each time and filing what it finds as
an issue here. Nothing to set up.

Pause it with:

```bash
gh variable set REVIEW_PAUSED --body 1 --repo xmrack/monero-review
```

`--body 0` resumes. Reviewing a specific PR by number still works while paused.

### If the schedule doesn't fire

GitHub runs scheduled workflows on a best-effort basis for public repos, and an
earlier every-30-minutes schedule here never fired once. The times above use an
odd minute and wide spacing, which is what GitHub's own guidance suggests.

If that still doesn't work, `scripts/drip.sh` does the same review on your own
machine from cron, with no credentials:

```
17 2,6,10,14,18,22 * * * /home/jack/Desktop/monero-review/scripts/drip.sh >> /tmp/monero-review.log 2>&1
```

## Where things are

`.claude/skills/monero-security-review/SKILL.md` is the review itself — edit
that if the output isn't sharp enough. `scripts/select_prs.py` decides which PR
is next and skips ones already reviewed.
