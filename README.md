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

The workflow runs itself every 5 minutes (GitHub's shortest allowed interval),
reviewing one PR each time and filing what it finds as an issue here. Only one
review runs at a time, so this works out at roughly 6 an hour at most.

Pause it with:

```bash
gh variable set REVIEW_PAUSED --body 1 --repo xmrack/monero-review
```

`--body 0` resumes. Reviewing a specific PR by number still works while paused.

### If the schedule doesn't fire

GitHub runs scheduled workflows on a best-effort basis for public repos, and an
earlier every-30-minutes schedule here never fired once — it ran at :00 and :30,
the most congested minutes, which GitHub's own guidance says to avoid. The times
above are odd minutes nobody else picks.

If that still doesn't work, `scripts/drip.sh` does the same review on your own
machine from cron, with no credentials:

```
7,27,47 * * * * /home/jack/Desktop/monero-review/scripts/drip.sh >> /tmp/monero-review.log 2>&1
```

## Where things are

`.claude/skills/monero-security-review/SKILL.md` is the review itself — edit
that if the output isn't sharp enough. `scripts/select_prs.py` decides which PR
is next and skips ones already reviewed.
