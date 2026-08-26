# monero-review

Automated security review of monero-project/monero pull requests.

It pulls down a PR's head commit, has Claude read the diff against a
Monero-specific review skill, and files what it finds as an issue here. A second
pass then tries to knock down every finding before anything gets filed, since
most first-pass findings turn out to be wrong. Nothing from the PR is ever built
or executed, and Claude has no network or GitHub access — it just writes a file,
and the workflow decides what to do with it.

Reviews run on their own every 30 minutes, one PR at a time.

## Run one yourself

```bash
gh workflow run security-review.yml --repo xmrack/monero-review -f pr=11155
```

Or locally, which needs no secrets and no runner:

```bash
./review-local.sh 11155
```

## Stop it

```bash
gh variable set REVIEW_PAUSED --body 1 --repo xmrack/monero-review
```

Use `--body 0` to start it again. Manual runs still work while it's paused.

## Where things are

`.claude/skills/monero-security-review/SKILL.md` is the review itself — edit
that if the output isn't sharp enough. The schedule and its settings
(`MAX_AGE_DAYS`, `BATCH`) are at the top of
`.github/workflows/security-review.yml`.
