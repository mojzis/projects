#!/usr/bin/env bash
# Merge open Dependabot PRs across all of an owner's repos, where safe.
#
# "Where safe" = PR is MERGEABLE and mergeStateStatus is CLEAN (checks green,
# no conflicts). UNSTABLE (red/pending checks), BLOCKED, and CONFLICTING PRs
# are skipped and reported, never force-merged.
#
# Usage:
#   scripts/merge-dependabot.sh <owner> [--dry-run] [repo ...]
#
#   <owner>        GitHub user/org (e.g. mojzis)
#   --dry-run      List what would be merged; merge nothing
#   [repo ...]     Optional explicit repo names; default = all of the owner's repos
#
# Requires: gh (authenticated), jq.
#
# Two failure modes you WILL hit and how to clear them:
#
#   1. "refusing to allow an OAuth App to create or update workflow ... without
#      `workflow` scope" — any PR touching .github/workflows/* is refused.
#      Fix once:  gh auth refresh -h github.com -s workflow   (interactive)
#      then re-run this script.
#
#   2. "Pull Request has merge conflicts" — the Dependabot cascade: once one PR
#      edits pyproject.toml / lockfile, its siblings conflict. Tell Dependabot to
#      rebase the survivors, wait for CI, then re-run:
#         scripts/merge-dependabot.sh <owner> --rebase-conflicts
set -euo pipefail

# Log dir lives at the repo root (gitignored), one timestamped file per run.
log_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/logs"
mkdir -p "$log_dir"
log_file="$log_dir/merge-$(date +%Y%m%d-%H%M%S).log"

owner="${1:-}"
if [[ -z "$owner" || "$owner" == -* ]]; then
  echo "usage: $0 <owner> [--dry-run] [--rebase-conflicts] [repo ...]" >&2
  exit 2
fi
shift

dry_run=false
rebase_conflicts=false
repos=()
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=true ;;
    --rebase-conflicts) rebase_conflicts=true ;;
    -*) echo "unknown flag: $arg" >&2; exit 2 ;;
    *) repos+=("$arg") ;;
  esac
done

# Default: every repo the owner has (matches what gh-monitor reports on).
if [[ ${#repos[@]} -eq 0 ]]; then
  mapfile -t repos < <(gh repo list "$owner" --no-archived --limit 1000 \
    --json name --jq '.[].name')
fi

ok=0; skip=0; fail=0; rebased=0
merged_repos=()
for r in "${repos[@]}"; do
  prs=$(gh pr list -R "$owner/$r" --state open \
        --json number,author,mergeStateStatus --limit 100 2>/dev/null \
        | jq -c '.[] | select(.author.login=="app/dependabot")')
  [[ -z "$prs" ]] && continue

  while IFS= read -r pr; do
    [[ -z "$pr" ]] && continue
    n=$(jq -r '.number' <<<"$pr")
    state=$(jq -r '.mergeStateStatus' <<<"$pr")

    if [[ "$state" == "CLEAN" ]]; then
      if $dry_run; then
        echo "WOULD-MERGE $owner/$r #$n"
      elif gh pr merge -R "$owner/$r" "$n" --squash --delete-branch 2>/tmp/dmerge.err; then
        echo "OK          $owner/$r #$n"; ok=$((ok+1)); merged_repos+=("$r")
      else
        echo "FAIL        $owner/$r #$n -> $(tr -d '\n' </tmp/dmerge.err)"; fail=$((fail+1))
      fi
    elif [[ ( "$state" == "DIRTY" || "$state" == "UNKNOWN" ) ]] && $rebase_conflicts; then
      gh pr comment -R "$owner/$r" "$n" --body "@dependabot rebase" >/dev/null
      echo "REBASE      $owner/$r #$n (asked dependabot to rebase)"; rebased=$((rebased+1))
    else
      echo "SKIP        $owner/$r #$n ($state)"; skip=$((skip+1))
    fi
  done <<<"$prs"
done
rm -f /tmp/dmerge.err

# Brief log: which repos had merges and so need a local fetch/pull.
if [[ ${#merged_repos[@]} -gt 0 ]]; then
  printf '%s\n' "${merged_repos[@]}" | sort -u >"$log_file"
  echo "fetch these: $log_file"
fi

echo "=== merged: $ok  skipped: $skip  failed: $fail  rebase-requested: $rebased ==="
