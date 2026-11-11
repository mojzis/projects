#!/usr/bin/env bash
# Roll new releases of our own tools out to every repo that depends on them.
#
# "Our own tools" = the PyPI packages listed in <owner>/aesop content/tools.yaml
# (the agentic-python showcase). For each of the owner's repos whose
# pyproject.toml lists one of them and is behind the latest PyPI release:
#
#   1. clone into a throwaway temp dir, branch tool-bump/<tool>-<version>
#   2. bump exactly the stale tools: rewrite a ">=X" floor in pyproject.toml to
#      the new version, and `uv lock --upgrade-package <tool>` when uv.lock is
#      tracked. Lock bump only for bare specs like "biston" and for runtime
#      deps under [project] (a published package's floor is its own promise)
#   3. run the repo's tests locally (`uv run poe check`, else `uv run pytest`)
#   4. push, open a PR
#   5. wait for the PR's CI, squash-merge when green
#
# Stateless: "is there a new version" is answered by comparing PyPI against each
# repo's floor/lock, so re-running is safe and picks up where a run stopped — an
# open tool-bump/* PR is waited on and merged instead of opening another.
#
# Usage:
#   scripts/bump-tools.sh <owner> [--dry-run] [--tool NAME]... [--no-test]
#                         [--no-merge] [repo ...]
#
#   --dry-run     list what would be bumped; clone/push nothing
#   --tool NAME   only consider this tool (PyPI name; repeatable)
#   --no-test     skip the local test run; the PR's CI is then the only gate,
#                 so a repo without PR CI is left open, never merged untested
#   --no-merge    open PRs but do not merge them
#   [repo ...]    explicit repo names; default = all non-archived repos
#
# Requires: gh (authenticated), jq, uv, curl.
#
# Not handled (reported, never forced):
#   - specs other than ">=" (==, ~=, <): the lock cannot move -> STUCK
#   - `exclude-newer` hiding the fresh release -> STUCK
#   - floors in uv-workspace member pyproject.toml files (only the root is read)
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log_dir="$root/logs"
mkdir -p "$log_dir"
stamp="$(date +%Y%m%d-%H%M%S)"

usage() {
  echo "usage: $0 <owner> [--dry-run] [--tool NAME]... [--no-test] [--no-merge] [repo ...]" >&2
  exit 2
}

owner="${1:-}"
[[ -z "$owner" || "$owner" == -* ]] && usage
shift

dry_run=false; run_tests=true; do_merge=true
only_tools=(); repos=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) dry_run=true ;;
    --no-test) run_tests=false ;;
    --no-merge) do_merge=false ;;
    --tool) shift; [[ $# -gt 0 ]] || usage; only_tools+=("$1") ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *) repos+=("$1") ;;
  esac
  shift
done

raw() { gh api -H "Accept: application/vnd.github.raw" "repos/$owner/$1/contents/$2" 2>/dev/null; }

# version_lt A B: true when A sorts strictly before B.
version_lt() {
  [[ "$1" != "$2" && "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n1)" == "$1" ]]
}

# locked_version TOOL: reads uv.lock text on stdin.
locked_version() {
  awk -v t="$1" '
    $0 == "name = \"" t "\"" { hit = 1; next }
    hit && /^version = / { gsub(/^version = "|"$/, ""); print; exit }
    /^\[\[package\]\]/ { hit = 0 }'
}

# Floors are only ours to move in dev/tooling sections. A floor under [project]
# (dependencies, optional-dependencies) is a published compatibility promise of
# that package, so it is left alone and only the lock moves.
#
# floor_of TOOL: reads pyproject.toml on stdin; prints the X of a one-per-line
# dev dependency entry "tool>=X" / "tool[extra]>=X" (empty when bare or absent).
floor_of() {
  awk -v t="$1" '
    /^\[/ { runtime = ($0 ~ /^\[project(\.optional-dependencies)?\]/) }
    !runtime && $0 ~ ("^[ \t]*\"" t "(\\[[^]]*\\])?[ \t]*>=") {
      sub(/^[^>]*>=[ \t]*/, ""); sub(/[",; ].*$/, ""); print; exit
    }'
}

# set_floor TOOL VERSION FILE: rewrite that same entry in place.
set_floor() {
  awk -v t="$1" -v v="$2" '
    /^\[/ { runtime = ($0 ~ /^\[project(\.optional-dependencies)?\]/) }
    !runtime && $0 ~ ("^[ \t]*\"" t "(\\[[^]]*\\])?[ \t]*>=") {
      sub(/>=[ \t]*[0-9][^",; ]*/, ">=" v)
    }
    { print }' "$3" >"$3.new" && mv "$3.new" "$3"
}

has_dep() { grep -qP "^\s*\"$1(\[[^\]]*\])?\s*([<>=~!;,][^\"]*)?\",?\s*(#.*)?$"; }

# --- tools and their latest versions -----------------------------------------
mapfile -t tools < <(raw aesop content/tools.yaml \
  | grep -oP 'pypi\.org/project/\K[^/\s"]+' | sort -u)
[[ ${#tools[@]} -gt 0 ]] || { echo "no tools found in $owner/aesop content/tools.yaml" >&2; exit 1; }
if [[ ${#only_tools[@]} -gt 0 ]]; then
  for t in "${only_tools[@]}"; do
    printf '%s\n' "${tools[@]}" | grep -qxF "$t" \
      || { echo "not an aesop tool: $t (known: ${tools[*]})" >&2; exit 2; }
  done
  tools=("${only_tools[@]}")
fi

declare -A latest
for t in "${tools[@]}"; do
  latest[$t]="$(curl -fsS "https://pypi.org/pypi/$t/json" | jq -r '.info.version')"
  echo "TOOL        $t ${latest[$t]}"
done

if [[ ${#repos[@]} -eq 0 ]]; then
  mapfile -t repos < <(gh repo list "$owner" --no-archived --source --limit 1000 \
    --json name --jq '.[].name' | sort)
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# Queue for the merge phase: "repo number tested(true|false)".
queue=()
bumped=0; stuck=0; test_failed=0; merged=0; left_open=0
merged_repos=()

# --- phase 1: bump, test, open PRs -------------------------------------------
for r in "${repos[@]}"; do
  pyproject="$(raw "$r" pyproject.toml)" || continue
  [[ -n "$pyproject" ]] || continue
  self="$(grep -m1 -oP '^name\s*=\s*"\K[^"]+' <<<"$pyproject" || true)"
  lock="$(raw "$r" uv.lock || true)"

  stale=()   # tools to bump in this repo
  notes=()   # "tool old->new" for output and the PR
  for t in "${tools[@]}"; do
    [[ "$t" == "$self" ]] && continue
    has_dep "$t" <<<"$pyproject" || continue
    floor="$(floor_of "$t" <<<"$pyproject")"
    locked="$(locked_version "$t" <<<"$lock")"
    new="${latest[$t]}"
    # Show the floor when it is the stale part (the lock may already be current).
    if [[ -n "$floor" ]] && version_lt "$floor" "$new"; then
      stale+=("$t"); notes+=("$t >=$floor -> $new")
    elif [[ -n "$locked" ]] && version_lt "$locked" "$new"; then
      stale+=("$t"); notes+=("$t $locked -> $new")
    fi
  done
  [[ ${#stale[@]} -gt 0 ]] || continue
  summary="$(IFS=,; echo "${notes[*]}" | sed 's/,/, /g')"

  open_pr="$(gh pr list -R "$owner/$r" --state open --json number,headRefName \
    --jq '[.[] | select(.headRefName | startswith("tool-bump/"))][0].number // empty')"
  if [[ -n "$open_pr" ]]; then
    echo "PENDING     $owner/$r #$open_pr (open tool-bump PR; $summary)"
    queue+=("$r $open_pr false")
    continue
  fi

  if $dry_run; then
    echo "WOULD-BUMP  $owner/$r: $summary"
    continue
  fi

  dir="$work/$r"
  log="$log_dir/bump-$stamp-$r.log"
  if ! gh repo clone "$owner/$r" "$dir" -- -q --depth 1 >"$log" 2>&1; then
    echo "FAIL        $owner/$r clone failed ($log)"; continue
  fi

  upgrade_args=()
  for t in "${stale[@]}"; do
    set_floor "$t" "${latest[$t]}" "$dir/pyproject.toml"
    upgrade_args+=(--upgrade-package "$t")
  done

  files=(pyproject.toml)
  if git -C "$dir" ls-files --error-unmatch uv.lock >/dev/null 2>&1; then
    files+=(uv.lock)
    if ! (cd "$dir" && env -u VIRTUAL_ENV uv lock "${upgrade_args[@]}") >>"$log" 2>&1; then
      echo "STUCK       $owner/$r uv lock failed ($log)"; stuck=$((stuck+1)); continue
    fi
    behind=()
    for t in "${stale[@]}"; do
      got="$(locked_version "$t" <"$dir/uv.lock")"
      [[ "$got" == "${latest[$t]}" ]] || behind+=("$t=$got")
    done
    if [[ ${#behind[@]} -gt 0 ]]; then
      echo "STUCK       $owner/$r lock did not reach latest: ${behind[*]} (pin or exclude-newer?)"
      stuck=$((stuck+1)); continue
    fi
  fi

  if git -C "$dir" diff --quiet -- "${files[@]}"; then
    echo "NOOP        $owner/$r nothing changed ($summary)"; continue
  fi

  tested=false
  if $run_tests; then
    if grep -qE '^check\s*=|^\[tool\.poe\.tasks\.check\]' "$dir/pyproject.toml"; then
      test_cmd=(uv run poe check)
    elif [[ -d "$dir/tests" ]]; then
      test_cmd=(uv run pytest -q)
    else
      test_cmd=()
    fi
    if [[ ${#test_cmd[@]} -gt 0 ]]; then
      echo "TEST        $owner/$r: ${test_cmd[*]}"
      if ! (cd "$dir" && env -u VIRTUAL_ENV "${test_cmd[@]}") >>"$log" 2>&1; then
        echo "TEST-FAIL   $owner/$r ($summary) -> $log"
        test_failed=$((test_failed+1)); continue
      fi
      tested=true
    fi
  fi

  branch="tool-bump/$(for t in "${stale[@]}"; do printf '%s-%s_' "$t" "${latest[$t]}"; done)"
  branch="${branch%_}"
  # Many tools at once (first rollout to a repo): keep the branch name short.
  [[ ${#stale[@]} -gt 2 ]] && branch="tool-bump/${#stale[@]}-tools-$stamp"
  title="Bump $(sed -E 's/ [^ ,]+ -> / to /g' <<<"$summary")"
  body="$(printf 'Automated by `scripts/bump-tools.sh` (mojzis/projects).\n\n'
          printf -- '- %s\n' "${notes[@]}"
          printf '\nLocal tests: %s\n' "$($tested && echo "passed (\`${test_cmd[*]}\`)" || echo "not run")")"
  if (cd "$dir" \
        && git checkout -q -b "$branch" \
        && git commit -q -m "$title" -- "${files[@]}" \
        && git push -q --force origin "$branch") >>"$log" 2>&1 \
     && url="$(gh pr create -R "$owner/$r" --head "$branch" \
                 --title "$title" --body "$body" 2>>"$log")"; then
    n="${url##*/}"
    echo "PR          $owner/$r #$n: $summary"
    bumped=$((bumped+1))
    queue+=("$r $n $tested")
  else
    echo "FAIL        $owner/$r push/PR failed ($log)"
  fi
  rm -rf "$dir"
done

# --- phase 2: wait for CI, merge ---------------------------------------------
# has_checks REPO PR: true once the PR reports at least one check. Polls briefly
# because checks register a few seconds after the PR opens.
has_checks() {
  local i count
  for i in 1 2 3 4 5 6; do
    count="$(gh pr view -R "$owner/$1" "$2" --json statusCheckRollup --jq '.statusCheckRollup | length')"
    [[ "$count" -gt 0 ]] && return 0
    sleep 10
  done
  return 1
}

if $do_merge && ! $dry_run; then
  for item in "${queue[@]}"; do
    read -r r n tested <<<"$item"
    if has_checks "$r" "$n"; then
      if ! gh pr checks -R "$owner/$r" "$n" --watch --fail-fast --interval 15 >/dev/null 2>&1; then
        echo "CI-FAIL     $owner/$r #$n (left open)"; left_open=$((left_open+1)); continue
      fi
    elif [[ "$tested" != true ]]; then
      echo "UNTESTED    $owner/$r #$n (no PR CI, no local test run; left open)"
      left_open=$((left_open+1)); continue
    fi
    if err="$(gh pr merge -R "$owner/$r" "$n" --squash --delete-branch 2>&1)"; then
      echo "MERGED      $owner/$r #$n"; merged=$((merged+1)); merged_repos+=("$r")
    else
      echo "FAIL        $owner/$r #$n merge -> $(tr -d '\n' <<<"$err")"; left_open=$((left_open+1))
    fi
  done
elif ! $dry_run; then
  left_open=${#queue[@]}
fi

# Which local clones are now behind (same convention as merge-dependabot.sh).
if [[ ${#merged_repos[@]} -gt 0 ]]; then
  printf '%s\n' "${merged_repos[@]}" | sort -u >"$log_dir/bump-$stamp.log"
  echo "fetch these: $log_dir/bump-$stamp.log"
fi

echo "=== PRs opened: $bumped  merged: $merged  left open: $left_open  test-failed: $test_failed  stuck: $stuck ==="
