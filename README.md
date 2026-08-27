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

`scripts/drip.sh` reviews the next unreviewed PR, one per run. Put it in cron:

```bash
crontab -e
```

```
*/30 * * * * /home/jack/Desktop/monero-review/scripts/drip.sh >> /tmp/monero-review.log 2>&1
```

It needs no credentials — the `claude` CLI is already authenticated and picking
the next PR only reads public data. Watch it with `tail /tmp/monero-review.log`.

There's deliberately no `schedule:` in the workflow. GitHub never fired one for
this repo despite the config being correct, so the drip lives in crontab where
it actually runs.

To stop it, comment out the crontab line.

## Where things are

`.claude/skills/monero-security-review/SKILL.md` is the review itself — edit
that if the output isn't sharp enough. `scripts/select_prs.py` decides which PR
is next and skips ones already reviewed.
