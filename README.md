# monero-review

Automated first-pass security review of `monero-project/monero` pull requests.

This repo contains no Monero source. It fetches a PR's head commit on demand
(`refs/pull/N/head` is readable on any public repo), runs Claude against the
diff with a Monero-specific review skill, and files the result here as an issue.
Upstream is never modified and does not need to know this exists.

## Contents

| Path | What it is |
| --- | --- |
| `.claude/skills/monero-security-review/SKILL.md` | The review instructions. The part worth iterating on. |
| `.github/workflows/security-review.yml` | Runs a review on GitHub-hosted runners, on demand or on a schedule. |
| `review-local.sh` | The same review, run locally against your own `claude` CLI. No secrets, no runner. |

## Setup

Requires the GitHub CLI (`sudo apt install gh`, then `gh auth login`).

```bash
gh repo create xmrack/monero-review --public --source . --push
```

Generate a token from your Claude subscription and store it as a repo secret:

```bash
claude setup-token
gh secret set CLAUDE_CODE_OAUTH_TOKEN --repo xmrack/monero-review
```

## Who can run it

`workflow_dispatch` requires **write access** on this repo, enforced by GitHub.
That is the entire access-control mechanism — to let a developer trigger
reviews, add them as a collaborator:

```bash
gh api -X PUT repos/xmrack/monero-review/collaborators/USERNAME -f permission=push
```

Note that every run spends from the Claude subscription behind
`CLAUDE_CODE_OAUTH_TOKEN`, which is tied to one person's account and is not
spend-capped. Keep the collaborator list tight, and re-run `claude setup-token`
to rotate if it changes.

## Running a review

```bash
gh workflow run security-review.yml -f pr=9876
```

Or the Actions tab → Monero Security Review → Run workflow. Findings appear in
three places: the run's summary page (rendered Markdown), an issue in this repo
labelled `pr-9876`, and a `review.md` artifact.

Locally, with no GitHub involvement at all:

```bash
./review-local.sh 9876
```

## The daily sweep

The `schedule:` block in the workflow is commented out deliberately. Run a few
reviews by hand first, see what they cost against your subscription limits, then
enable it. As configured it reviews at most 4 non-draft PRs updated in the last
72 hours, one at a time, on Sonnet. Manual dispatches default to Opus.

Deduplication is keyed on **head SHA**, not PR number. A PR sitting untouched is
reviewed once; a PR that gets force-pushed three times is reviewed three times;
a PR that collects twenty comments and no new commits is reviewed once. Cost
tracks actual code churn. Because the SHA guard is the real dedup, the 72-hour
lookback can be generous — over-selection costs nothing.

A failed run deliberately files no issue, so it leaves no dedup marker and gets
retried on the next sweep rather than being silently blackholed.

## Design notes

**Claude has no outward write capability.** Its allowed tools are `Read`,
`Grep`, `Glob`, `Write`, and three read-only git subcommands. No GitHub API, no
MCP server, no network. It produces `review.md`; the workflow — plain bash, not
the model — decides what happens to that file.

This matters because the code under review is written by strangers and this
tooling is not hardened against prompt injection. Under this design a malicious
instruction buried in a diff has nowhere to go: the worst it achieves is a
misleading report, which a human reads before anything else happens.

That constraint is also why reviews are not posted as comments on upstream PRs.
Commenting back would mean handing a write capability to a process whose input
is untrusted. If a finding is real, take it upstream yourself, in your own
words.

**Nothing from the PR is ever executed.** The job clones, diffs, and greps. It
never configures, compiles, or runs Monero. Building PRs under sanitizers is a
worthwhile thing to automate, but it means executing attacker-authored code and
belongs on a self-hosted runner, not here.

**Treat output as a first pass, not a verdict.** The value is in triage
throughput across 294 open PRs, not in the model's confidence.
