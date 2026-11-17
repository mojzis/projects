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
#                         [--no-merge] [-j N] [--timeout S] [repo ...]
#
#   --dry-run     list what would be bumped; clone/push nothing
#   --tool NAME   only consider this tool (PyPI name; repeatable)
#   --no-test     skip the local test run; the PR's CI is then the only gate,
#                 so a repo without PR CI is left open, never merged untested
#   --no-merge    open PRs but do not merge them
#   -j N          repos bumped/tested in parallel (default 4)
#   --timeout S   seconds to wait for PR checks before leaving PRs open (default 1800)
#   [repo ...]    explicit repos (name or owner/name); default = all non-archived
#                 repos + extra-repos.txt
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
  echo "usage: $0 <owner> [--dry-run] [--tool NAME]... [--no-test] [--no-merge] [-j N] [--timeout S] [repo ...]" >&2
  exit 2
}

owner="${1:-}"
[[ -z "$owner" || "$owner" == -* ]] && usage
shift

dry_run=false; run_tests=true; do_merge=true; max_jobs=4; timeout=1800
only_tools=(); repos=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) dry_run=true ;;
    --no-test) run_tests=false ;;
    --no-merge) do_merge=false ;;
    -j) shift; [[ "${1:-}" =~ ^[1-9][0-9]*$ ]] || usage; max_jobs="$1" ;;
    --timeout) shift; [[ "${1:-}" =~ ^[0-9]+$ ]] || usage; timeout="$1" ;;
    --tool) shift; [[ $# -gt 0 ]] || usage; only_tools+=("$1") ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *) repos+=("$1") ;;
  esac
  shift
done

raw() { gh api -H "Accept: application/vnd.github.raw" "repos/$1/contents/$2" 2>/dev/null; }

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
mapfile -t tools < <(raw "$owner/aesop" content/tools.yaml \
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

# Repos are owner/name from here on. Default: the owner's repos plus
# extra-repos.txt (repos in other orgs, e.g. changelog-chronicles/changelog).
if [[ ${#repos[@]} -eq 0 ]]; then
  mapfile -t repos < <(gh repo list "$owner" --no-archived --source --limit 1000 \
    --json nameWithOwner --jq '.[].nameWithOwner' | sort)
  extra="$(dirname "${BASH_SOURCE[0]}")/../extra-repos.txt"
  [[ -f "$extra" ]] && mapfile -t -O "${#repos[@]}" repos < <(grep -Ev '^\s*(#|$)' "$extra")
fi
for i in "${!repos[@]}"; do
  [[ "${repos[$i]}" == */* ]] || repos[i]="$owner/${repos[$i]}"
done

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT


# Status lines of the whole run, also counted for the summary. Phase 1 jobs append
# merge-queue entries ("repo number tested(true|false)") to $work/queue.
status_file="$work/status"
: >"$status_file"
: >"$work/queue"
say() { echo "$*" | tee -a "$status_file"; }

# --- phase 1: bump, test, open PRs (up to $max_jobs repos at once) ----------------
bump_one() {
  local r="$1" pyproject self lock t floor locked new summary open_pr dir log
  local stale=() notes=() upgrade_args=() files=() behind=() test_cmd=() got tested
  local branch title body url n
  pyproject="$(raw "$r" pyproject.toml)" || return 0
  [[ -n "$pyproject" ]] || return 0
  self="$(grep -m1 -oP '^name\s*=\s*"\K[^"]+' <<<"$pyproject" || true)"
  lock="$(raw "$r" uv.lock || true)"

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
  [[ ${#stale[@]} -gt 0 ]] || return 0
  summary="$(IFS=,; echo "${notes[*]}" | sed 's/,/, /g')"

  open_pr="$(gh pr list -R "$r" --state open --json number,headRefName \
    --jq '[.[] | select(.headRefName | startswith("tool-bump/"))][0].number // empty')"
  if [[ -n "$open_pr" ]]; then
    say "PENDING     $r #$open_pr (open tool-bump PR; $summary)"
    echo "$r $open_pr false" >>"$work/queue"
    return 0
  fi

  if $dry_run; then
    say "WOULD-BUMP  $r: $summary"
    return 0
  fi

  dir="$work/${r##*/}"
  log="$log_dir/bump-$stamp-${r##*/}.log"
  if ! gh repo clone "$r" "$dir" -- -q --depth 1 >"$log" 2>&1; then
    say "FAIL        $r clone failed ($log)"; return 0
  fi

  for t in "${stale[@]}"; do
    set_floor "$t" "${latest[$t]}" "$dir/pyproject.toml"
    upgrade_args+=(--upgrade-package "$t")
  done

  files=(pyproject.toml)
  if git -C "$dir" ls-files --error-unmatch uv.lock >/dev/null 2>&1; then
    files+=(uv.lock)
    if ! (cd "$dir" && env -u VIRTUAL_ENV uv lock "${upgrade_args[@]}") >>"$log" 2>&1; then
      say "STUCK       $r uv lock failed ($log)"; return 0
    fi
    for t in "${stale[@]}"; do
      got="$(locked_version "$t" <"$dir/uv.lock")"
      [[ "$got" == "${latest[$t]}" ]] || behind+=("$t=$got")
    done
    if [[ ${#behind[@]} -gt 0 ]]; then
      say "STUCK       $r lock did not reach latest: ${behind[*]} (pin or exclude-newer?)"
      return 0
    fi
  fi

  if git -C "$dir" diff --quiet -- "${files[@]}"; then
    say "NOOP        $r nothing changed ($summary)"; return 0
  fi

  tested=false
  if $run_tests; then
    # Rust repos (maturin): the Python env has no test runner; CI is the gate.
    if [[ -f "$dir/Cargo.toml" ]]; then
      test_cmd=()
    elif grep -qE '^check\s*=|^\[tool\.poe\.tasks\.check\]' "$dir/pyproject.toml"; then
      test_cmd=(uv run poe check)
    elif [[ -d "$dir/tests" ]]; then
      test_cmd=(uv run pytest -q)
    fi
    if [[ ${#test_cmd[@]} -gt 0 ]]; then
      say "TEST        $r: ${test_cmd[*]}"
      if ! (cd "$dir" && env -u VIRTUAL_ENV "${test_cmd[@]}") >>"$log" 2>&1; then
        say "TEST-FAIL   $r ($summary) -> $log"
        return 0
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
     && url="$(gh pr create -R "$r" --head "$branch" \
                 --title "$title" --body "$body" 2>>"$log")"; then
    n="${url##*/}"
    say "PR          $r #$n: $summary"
    echo "$r $n $tested" >>"$work/queue"
  else
    say "FAIL        $r push/PR failed ($log)"
  fi
  rm -rf "$dir"
}

for r in "${repos[@]}"; do
  while [[ "$(jobs -rp | wc -l)" -ge "$max_jobs" ]]; do wait -n || true; done
  bump_one "$r" &
done
wait

# --- phase 2: wait for CI, merge ---------------------------------------------
# One polling loop over every queued PR, so CI runs are waited on side by side.
# Merge on mergeStateStatus CLEAN (GitHub's own verdict: mergeable, checks green);
# a single failed check is CI-FAIL. Polling instead of `gh pr checks --watch`,
# which hung forever on a check run GitHub left "in_progress" after it succeeded.
# PRs with no checks at all: merged when tested locally, else UNTESTED.
pr_state() {
  gh pr view -R "$1" "$2" --json mergeStateStatus,statusCheckRollup --jq '
    [.statusCheckRollup[] | (.conclusion // .state // "")] as $c
    | if ($c | map(select(. == "FAILURE" or . == "ERROR" or . == "CANCELLED"
                         or . == "TIMED_OUT" or . == "ACTION_REQUIRED")) | length) > 0
        then "failed"
      elif ($c | length) == 0 then "nochecks"
      elif .mergeStateStatus == "CLEAN" then "clean"
      else "waiting" end'
}

merge_pr() {
  local err
  if err="$(gh pr merge -R "$1" "$2" --squash --delete-branch 2>&1)"; then
    say "MERGED      $1 #$2"
  else
    say "FAIL        $1 #$2 merge -> $(tr -d '\n' <<<"$err")"
  fi
}

mapfile -t queue <"$work/queue"
if $do_merge && ! $dry_run && [[ ${#queue[@]} -gt 0 ]]; then
  start=$SECONDS
  while [[ ${#queue[@]} -gt 0 ]]; do
    waiting=()
    for item in "${queue[@]}"; do
      read -r r n tested <<<"$item"
      case "$(pr_state "$r" "$n" || echo waiting)" in
        clean) merge_pr "$r" "$n" ;;
        failed) say "CI-FAIL     $r #$n (left open)" ;;
        nochecks)
          # Checks register a few seconds after the PR opens; give them a minute.
          if (( SECONDS - start < 60 )); then waiting+=("$item")
          elif [[ "$tested" == true ]]; then merge_pr "$r" "$n"
          else say "UNTESTED    $r #$n (no PR CI, no local test run; left open)"
          fi ;;
        *) waiting+=("$item") ;;
      esac
    done
    queue=("${waiting[@]}")
    [[ ${#queue[@]} -gt 0 ]] || break
    if (( SECONDS - start > timeout )); then
      for item in "${queue[@]}"; do
        read -r r n _ <<<"$item"
        say "TIMEOUT     $r #$n (checks still running after ${timeout}s; left open)"
      done
      break
    fi
    sleep 20
  done
fi

count() { grep -c "^$1 " "$status_file" || true; }
merged="$(count MERGED)"
if $dry_run; then
  left_open=0
elif $do_merge; then
  left_open=$(( $(count CI-FAIL) + $(count UNTESTED) + $(count TIMEOUT) + $(grep -c ' merge -> ' "$status_file" || true) ))
else
  left_open="$(wc -l <"$work/queue")"
fi

# Which local clones are now behind (same convention as merge-dependabot.sh).
if [[ "$merged" -gt 0 ]]; then
  grep '^MERGED ' "$status_file" | awk '{print $2}' | sort -u >"$log_dir/bump-$stamp.log"
  echo "fetch these: $log_dir/bump-$stamp.log"
fi

echo "=== PRs opened: $(count PR)  merged: $merged  left open: $left_open  test-failed: $(count TEST-FAIL)  stuck: $(count STUCK) ==="
