#!/usr/bin/env bash
# List local git repos that are NOT in the standard state.
#
# Standard state = on the default branch (main) AND clean (no uncommitted
# changes, nothing staged, no untracked files). Anything else is reported:
#   - on a branch other than main (or detached HEAD)
#   - uncommitted / staged / untracked changes
#   - ahead of / behind upstream (informational, still flagged)
#
# Usage:
#   scripts/repo-states.sh [dir] [--branch NAME] [--quiet]
#
#   [dir]            Directory holding git clones (default: ~/git)
#   --branch NAME    Branch considered "standard" (default: main)
#   --quiet          Print only non-standard repos, no summary line
#
# Exit status is 1 when any non-standard repo is found, else 0.
set -euo pipefail

dir="${HOME}/git"
standard_branch="main"
quiet=false

args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch) standard_branch="${2:?--branch needs a value}"; shift 2 ;;
    --quiet) quiet=true; shift ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *) args+=("$1"); shift ;;
  esac
done
[[ ${#args[@]} -gt 0 ]] && dir="${args[0]}"

if [[ ! -d "$dir" ]]; then
  echo "not a directory: $dir" >&2
  exit 2
fi

total=0; nonstandard=0
for repo in "$dir"/*/; do
  [[ -d "$repo/.git" ]] || continue
  total=$((total+1))

  branch=$(git -C "$repo" symbolic-ref --short -q HEAD || echo "(detached)")

  reasons=()
  [[ "$branch" != "$standard_branch" ]] && reasons+=("branch=$branch")
  [[ -n "$(git -C "$repo" status --porcelain)" ]] && reasons+=("dirty")

  # Upstream divergence (only if an upstream is configured).
  if upstream=$(git -C "$repo" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null); then
    counts=$(git -C "$repo" rev-list --left-right --count "HEAD...$upstream" 2>/dev/null || echo "0	0")
    ahead=${counts%%	*}; behind=${counts##*	}
    [[ "$ahead"  -gt 0 ]] && reasons+=("ahead=$ahead")
    [[ "$behind" -gt 0 ]] && reasons+=("behind=$behind")
  fi

  if [[ ${#reasons[@]} -gt 0 ]]; then
    nonstandard=$((nonstandard+1))
    printf '%-30s %s\n' "$(basename "$repo")" "${reasons[*]}"
  fi
done

if ! $quiet; then
  echo "=== $nonstandard non-standard / $total repos in $dir ==="
fi

[[ $nonstandard -gt 0 ]] && exit 1 || exit 0
