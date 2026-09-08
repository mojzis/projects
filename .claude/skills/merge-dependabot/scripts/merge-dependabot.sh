#!/usr/bin/env bash
# Bulk-merge Dependabot PRs across an owner's repos.
#
#   merge-dependabot.sh <owner> [repo ...] [--dry-run] [--rebase-conflicts]
#
# Merges every MERGEABLE + CLEAN Dependabot PR (squash, delete branch) and
# reports everything else. Idempotent.
set -euo pipefail

DRY_RUN=0
REBASE_CONFLICTS=0
OWNER=""
REPOS=()

# Repos deliberately excluded from cross-repo work (see CLAUDE.md).
SKIP_REPOS=("sketchpy" "tyreach")

usage() {
  sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

for arg in "$@"; do
  case "$arg" in
    --dry-run)          DRY_RUN=1 ;;
    --rebase-conflicts) REBASE_CONFLICTS=1 ;;
    -h|--help)          usage 0 ;;
    -*)                 echo "unknown flag: $arg" >&2; usage 1 ;;
    *)                  if [[ -z "$OWNER" ]]; then OWNER="$arg"; else REPOS+=("$arg"); fi ;;
  esac
done

[[ -n "$OWNER" ]] || usage 1

skipped_repo() {
  local r=$1
  for s in "${SKIP_REPOS[@]}"; do [[ "$r" == "$s" ]] && return 0; done
  return 1
}

if [[ ${#REPOS[@]} -eq 0 ]]; then
  mapfile -t REPOS < <(
    gh repo list "$OWNER" --no-archived --limit 1000 --json name \
      --jq '.[].name' | sort
  )
fi

merged=(); blocked=(); conflicted=(); unstable=(); other=(); rebased=()

for repo in "${REPOS[@]}"; do
  if skipped_repo "$repo"; then
    echo "-- $OWNER/$repo (skipped by policy)"
    continue
  fi

  prs=$(gh pr list --repo "$OWNER/$repo" --state open --author "app/dependabot" \
        --json number,title,mergeStateStatus --limit 100 2>/dev/null || echo '[]')
  [[ "$(jq 'length' <<<"$prs")" -gt 0 ]] || continue

  echo "== $OWNER/$repo"
  while IFS=$'\t' read -r num state title; do
    label="$repo#$num ($state) $title"
    case "$state" in
      CLEAN)
        if [[ $DRY_RUN -eq 1 ]]; then
          echo "   would merge  #$num  $title"
          merged+=("$label")
        elif err=$(gh pr merge "$num" --repo "$OWNER/$repo" --squash --delete-branch 2>&1); then
          echo "   merged       #$num  $title"
          merged+=("$label")
        else
          echo "   FAILED       #$num  $title"
          echo "                $(head -n1 <<<"$err")"
          other+=("$label -- ${err//$'\n'/ }")
        fi
        ;;
      DIRTY)
        echo "   conflicts    #$num  $title"
        conflicted+=("$label")
        if [[ $REBASE_CONFLICTS -eq 1 && $DRY_RUN -eq 0 ]]; then
          gh pr comment "$num" --repo "$OWNER/$repo" --body "@dependabot rebase" >/dev/null
          echo "                asked dependabot to rebase"
          rebased+=("$label")
        fi
        ;;
      UNSTABLE|BLOCKED)
        echo "   $(tr '[:upper:]' '[:lower:]' <<<"$state")     #$num  $title"
        [[ "$state" == "BLOCKED" ]] && blocked+=("$label") || unstable+=("$label")
        ;;
      *)
        echo "   $state  #$num  $title"
        other+=("$label")
        ;;
    esac
  done < <(jq -r '.[] | [.number, .mergeStateStatus, .title] | @tsv' <<<"$prs")
done

summary() {
  local name=$1; shift
  [[ $# -gt 0 ]] || return 0
  echo
  echo "$name ($#):"
  printf '  %s\n' "$@"
}

echo
echo "---"
summary "$([[ $DRY_RUN -eq 1 ]] && echo 'Would merge' || echo 'Merged')" ${merged+"${merged[@]}"}
summary "Conflicts (rerun with --rebase-conflicts)" ${conflicted+"${conflicted[@]}"}
summary "Rebase requested" ${rebased+"${rebased[@]}"}
summary "CI red/pending" ${unstable+"${unstable[@]}"}
summary "Blocked (protection/review)" ${blocked+"${blocked[@]}"}
summary "Other" ${other+"${other[@]}"}
