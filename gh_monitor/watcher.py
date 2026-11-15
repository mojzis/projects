"""Keep a configured set of local clones in step with GitHub.

Meant to run unattended from a timer, so it only ever does what is safe without a
person: fast-forward pulls, and plain pushes for repos configured as two-way. Anything
else (dirty tree, other branch checked out, diverged history) is reported and left alone.
"""

import tomllib
from pathlib import Path

from .models import WatchAction, WatchDirection, WatchedRepo, WatchResult
from .process import run_command

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "watched.toml"


def load_watch_config(path: Path) -> list[WatchedRepo]:
    """Parse the watch config into repo entries.

    Top-level keys give defaults (`owner`, `dir`); each `[[repo]]` needs a `name` and may
    override `path`, `branch` and `direction`.
    """
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    owner = data.get("owner")
    base_dir = Path(data.get("dir", "~/git")).expanduser()

    repos = []
    for entry in data.get("repo", []):
        name = entry["name"]
        repo_owner = entry.get("owner", owner)
        if not repo_owner:
            raise ValueError(f"{path}: repo {name!r} has no owner (set top-level `owner`)")
        repos.append(
            WatchedRepo(
                name=name,
                path=Path(entry["path"]).expanduser() if "path" in entry else base_dir / name,
                clone_url=f"git@github.com:{repo_owner}/{name}.git",
                branch=entry.get("branch", "main"),
                direction=WatchDirection(entry.get("direction", "pull")),
            )
        )
    return repos


def _git(repo: Path, *args: str) -> tuple[bool, str]:
    return run_command(["git", *args], cwd=repo)


def _oneline(repo: Path, rev_range: str) -> list[str]:
    ok, out = _git(repo, "log", "--oneline", "--no-decorate", rev_range)
    return out.splitlines() if ok and out else []


def _ahead_behind(repo: Path) -> tuple[int, int] | None:
    ok, out = _git(repo, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")
    if not ok:
        return None
    ahead, behind = out.split()
    return int(ahead), int(behind)


def watch_repo(repo: WatchedRepo) -> WatchResult:
    """Run one pass over a repository: clone, fetch, then fast-forward or push."""
    if not (repo.path / ".git").exists():
        ok, out = run_command(["git", "clone", repo.clone_url, str(repo.path)])
        if not ok:
            return WatchResult(repo.name, WatchAction.ERROR, f"clone failed: {out}")
        return WatchResult(repo.name, WatchAction.CLONED, f"cloned to {repo.path}")

    ok, out = _git(repo.path, "fetch", "--prune", "origin")
    if not ok:
        return WatchResult(repo.name, WatchAction.ERROR, f"fetch failed: {out}")

    upstream = f"origin/{repo.branch}"
    _, current = _git(repo.path, "rev-parse", "--abbrev-ref", "HEAD")
    if current != repo.branch:
        incoming = _oneline(repo.path, f"{repo.branch}..{upstream}")
        return WatchResult(
            repo.name,
            WatchAction.SKIPPED_BRANCH,
            f"on {current!r}, not {repo.branch!r}; {len(incoming)} new on {upstream}",
            incoming,
        )

    _, status = _git(repo.path, "status", "--porcelain")
    if status:
        incoming = _oneline(repo.path, "HEAD..@{upstream}")
        return WatchResult(
            repo.name,
            WatchAction.SKIPPED_DIRTY,
            f"uncommitted changes; {len(incoming)} new on {upstream}",
            incoming,
        )

    return _move_commits(repo, upstream)


def _move_commits(repo: WatchedRepo, upstream: str) -> WatchResult:
    """On a clean tracked branch: fast-forward, push, or report a divergence."""
    counts = _ahead_behind(repo.path)
    if counts is None:
        return WatchResult(repo.name, WatchAction.ERROR, f"{repo.branch} has no upstream")
    ahead, behind = counts

    if ahead and behind:
        return WatchResult(
            repo.name,
            WatchAction.DIVERGED,
            f"diverged from {upstream}: {ahead} local, {behind} remote commits",
        )
    if behind:
        incoming = _oneline(repo.path, "HEAD..@{upstream}")
        ok, out = _git(repo.path, "merge", "--ff-only", "@{upstream}")
        if not ok:
            return WatchResult(repo.name, WatchAction.ERROR, f"fast-forward failed: {out}")
        return WatchResult(repo.name, WatchAction.PULLED, f"pulled {behind}", incoming)
    if ahead:
        outgoing = _oneline(repo.path, "@{upstream}..HEAD")
        if repo.direction is not WatchDirection.BOTH:
            return WatchResult(
                repo.name, WatchAction.LOCAL_AHEAD, f"{ahead} local commits not pushed", outgoing
            )
        ok, out = _git(repo.path, "push", "origin", repo.branch)
        if not ok:
            return WatchResult(repo.name, WatchAction.ERROR, f"push failed: {out}")
        return WatchResult(repo.name, WatchAction.PUSHED, f"pushed {ahead}", outgoing)
    return WatchResult(repo.name, WatchAction.CURRENT, "up to date")
