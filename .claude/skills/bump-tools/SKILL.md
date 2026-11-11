---
description: Roll a new release of one of our own tools (the aesop menagerie - biston, gerenuk, madoqua, ...) out to every repo that depends on it - bump, test, PR, merge.
allowed-tools: Bash, Read
argument-hint: <owner> [--dry-run] [--tool NAME] [--no-test] [--no-merge] [repo ...]
---

# Bump our own tools everywhere

After releasing a tool listed in `<owner>/aesop` `content/tools.yaml`, bring every
dependent repo up to it. Mechanical, so it is a script; no LLM per repo.

## When to use

A menagerie tool got a new PyPI release, or the user wants all repos on current
tool versions.

## Steps

1. **Survey**:
   ```bash
   scripts/bump-tools.sh <owner> --dry-run
   ```
2. **Roll out** (all tools, or one with `--tool`):
   ```bash
   scripts/bump-tools.sh <owner> --tool gerenuk
   ```
3. **Read the status lines**, deal with the leftovers below, re-run. It is
   stateless and idempotent: an open `tool-bump/*` PR is waited on and merged,
   not duplicated.

## What it does per repo

- Stale = dev floor (`"biston>=0.7.2"`) or `uv.lock` version below PyPI latest.
- Bumps only the stale tools: floor rewritten in place, `uv lock
  --upgrade-package <tool>` when `uv.lock` is tracked. Nothing else in the lock moves.
- Floors under `[project]` (runtime deps of a published package, e.g. gerenuk's
  `ty-find>=`) are never rewritten; only the lock moves there.
- A tool's own repo is skipped for that tool.
- Tests in a throwaway clone: `uv run poe check` if the repo defines it, else
  `uv run pytest -q`. A failure means no PR.
- PR, then merge once the PR's checks are green. No PR checks: merges on the
  local test pass alone. Neither: left open.

## Status lines

| Line | Meaning | Do |
|---|---|---|
| `PR` / `MERGED` | done | - |
| `TEST-FAIL` | local tests red with the new version; log path printed | read the log; real breakage in the new release vs. the repo needing env/secrets (then `--no-test` if it has CI) |
| `STUCK` | lock did not reach latest | `==`/`<` pin or `exclude-newer` in that repo; fix by hand |
| `CI-FAIL` | PR checks red, PR left open | check whether `main` is already red before blaming the bump |
| `UNTESTED` | no CI and no local tests ran | merge by hand after looking |
| `PENDING` | open bump PR from an earlier run | merged this run if its checks are green |

Judgment (a subagent, if many) is only for `TEST-FAIL` / `CI-FAIL`.

## Notes

- Just-published release not picked up: PyPI's JSON API or uv's index cache can
  lag a minute; re-run.
- Local clones under `~/git` are not touched; `logs/bump-<stamp>.log` lists the
  repos to pull (`gh-monitor sync <owner>`).
- Only root `pyproject.toml` is read; uv-workspace member floors are not bumped.
