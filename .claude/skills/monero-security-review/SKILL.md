---
name: monero-security-review
description: Security review of the changes in a Monero pull request.
allowed-tools: Read, Grep, Glob, Write, Bash(git diff:*), Bash(git log:*), Bash(git merge-base:*)
---

Review only the changes introduced by this pull request:

```
git diff $(git merge-base origin/master HEAD)...HEAD
```

Read `PR_CONTEXT.md` first if it exists — it holds the PR title and description.
Stated intent matters: "does this change do what it claims, and what else does it
do" is a sharper question than reading the diff cold.

Read surrounding code freely for context. Do not report pre-existing issues that
the diff does not touch or make reachable.

## Priorities, in order

1. **Consensus divergence.** Anything that could cause this node to accept or
   reject a block or transaction differently from the rest of the network.
   Changes to verification, serialization, hard-fork gating, or difficulty are
   in scope even when they look like refactors.

2. **Memory safety on untrusted input.** Trace whether the changed code is
   reachable from P2P blobs, RPC request bodies, wallet cache files, key-image
   blobs, or daemon responses to a wallet. Look for `resize()`/`reserve()` sized
   by an attacker-controlled count, unchecked indices, missing bounds checks,
   iterator or reference invalidation across container mutation, and lifetime
   bugs where an object outlives or is freed before its users.

3. **Cryptographic correctness.** Missing point or scalar validation, absent
   torsion and identity checks, non-constant-time comparison on secret data,
   RNG misuse, and any nonce or key-derivation reuse.

4. **Privacy.** Decoy selection, timing and traffic side channels, and
   information exposed over restricted RPC.

5. **Concurrency.** Shared mutable state touched from the refresh, RPC, and
   wallet threads without synchronisation.

6. **Resource exhaustion** reachable before authentication.

## Reporting

For each finding give:

- `file:line`
- The concrete attacker-controlled path that reaches it. If you cannot name the
  entry point and the sequence of calls, you do not have a finding.
- Impact, stated as what an attacker gains.
- A minimal fix.

Do not report style, naming, or performance without a denial-of-service
argument. Do not report theoretical issues you cannot trace to an input.
Prefer zero findings over speculation — a report full of maybes is worse than
an empty one, because someone has to spend real time refuting each entry.

When you are done, write your findings to `review.md` in the repository root as
GitHub-flavored Markdown. Lead with a one-paragraph summary of what the PR does
and your overall assessment, then the findings ordered most severe first. If
nothing meets the bar, say so plainly and explain what you checked. Write
nothing else and create no other files.
