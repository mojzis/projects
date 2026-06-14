---
description: Merge open Dependabot PRs across all of an owner's repos, where safe (CLEAN only), and handle the workflow-scope and merge-conflict cascade.
allowed-tools: Bash, Read
argument-hint: <owner> [--dry-run] [--rebase-conflicts] [repo ...]
---

# Merge Dependabot PRs

Bulk-merge the Dependabot PRs surfaced by `gh-monitor` (the dashboard at
mojzis.github.io/projects). Mechanical PRs (green checks, no conflicts) are
merged by script — no LLM per PR. Only the messy ones need judgment.

## When to use

User wants to clear open Dependabot PRs across many repos at once, e.g. after
reviewing the project dashboard.

## Decision: script, not subagents

For PRs that are **MERGEABLE + CLEAN**, merging is a pure `gh pr merge` loop.
An LLM/subagent adds cost and risk with zero benefit — use the script.

Reserve subagents for **UNSTABLE** PRs (red/pending checks): one diagnosis per
repo of *why* CI is red. Often a single repo-wide cause (e.g. the repo's own
`main` is already failing), not one cause per PR — check `main` first before
spinning up N agents.

## Steps

1. **Survey** — see counts and merge states before touching anything:
   ```bash
   scripts/merge-dependabot.sh <owner> --dry-run
   ```
2. **Merge the safe ones**:
   ```bash
   scripts/merge-dependabot.sh <owner>
   ```
   Squash-merges and deletes the branch for every CLEAN Dependabot PR. Skips and
   reports everything else.
3. **Clear the two expected failure buckets** (below), then re-run step 2.

`mergeStateStatus` cheat-sheet: `CLEAN` = merge it; `UNSTABLE` = checks
red/pending (judgment); `DIRTY` = conflicts; `BLOCKED` = branch protection/review.

## Failure bucket 1 — `workflow` scope

Any PR that edits `.github/workflows/*` fails with:

> refusing to allow an OAuth App to create or update workflow `…` without `workflow` scope

The `gh` token lacks the `workflow` scope. Fix once (interactive — the user must
run it; suggest typing it with the `!` prefix in the session):

```
gh auth refresh -h github.com -s workflow
```

Then re-run the merge script. This single fix unblocks the bulk of failures
(GitHub Actions version bumps).

## Failure bucket 2 — the conflict cascade

> Pull Request has merge conflicts

Dependabot opens several PRs touching the same `pyproject.toml` / lockfile. The
first to merge is fine; siblings then conflict — even though they were CLEAN at
survey time. Ask Dependabot to rebase the survivors, wait for CI to go green,
then re-run:

```bash
scripts/merge-dependabot.sh <owner> --rebase-conflicts   # posts "@dependabot rebase"
# …wait for CI…
scripts/merge-dependabot.sh <owner>                       # merge the now-CLEAN ones
```

## Notes

- Filters on author `app/dependabot` (the login `gh` reports for the Dependabot
  GitHub App).
- Defaults to all of the owner's non-archived repos; pass repo names to scope it.
- Idempotent: already-merged PRs simply aren't listed on re-run.
