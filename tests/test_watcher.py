"""Tests for the watcher, run against real throwaway git repos (bare remote + clones)."""

import subprocess
from pathlib import Path

import pytest

from gh_monitor.models import WatchAction, WatchDirection, WatchedRepo
from gh_monitor.watcher import load_watch_config, watch_repo


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def commit(repo: Path, name: str) -> None:
    (repo / name).write_text(name)
    git(repo, "add", name)
    git(repo, "commit", "-qm", f"add {name}")


@pytest.fixture
def remote(tmp_path, monkeypatch) -> Path:
    """A bare 'GitHub' remote with one commit on main."""
    for key, value in {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }.items():
        monkeypatch.setenv(key, value)
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", "-q", str(bare), str(seed))
    commit(seed, "a")
    git(seed, "push", "-q", "origin", "main")
    return bare


@pytest.fixture
def other(tmp_path, remote) -> Path:
    """Another clone standing in for changes made elsewhere (e.g. a merged PR)."""
    path = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(remote), str(path))
    return path


def make_repo(tmp_path: Path, remote: Path, direction=WatchDirection.PULL) -> WatchedRepo:
    return WatchedRepo(
        name="r", path=tmp_path / "local", clone_url=str(remote), direction=direction
    )


def push_from(other: Path, name: str) -> None:
    commit(other, name)
    git(other, "push", "-q", "origin", "main")


def test_clones_missing_repo(tmp_path, remote):
    repo = make_repo(tmp_path, remote)
    assert watch_repo(repo).action is WatchAction.CLONED
    assert (repo.path / "a").exists()


def test_current_when_nothing_changed(tmp_path, remote):
    repo = make_repo(tmp_path, remote)
    watch_repo(repo)
    assert watch_repo(repo).action is WatchAction.CURRENT


def test_fast_forwards_remote_commits(tmp_path, remote, other):
    repo = make_repo(tmp_path, remote)
    watch_repo(repo)
    push_from(other, "b")

    result = watch_repo(repo)

    assert result.action is WatchAction.PULLED
    assert (repo.path / "b").exists()
    assert [line.split(" ", 1)[1] for line in result.commits] == ["add b"]


def test_pull_only_repo_does_not_push(tmp_path, remote):
    repo = make_repo(tmp_path, remote)
    watch_repo(repo)
    commit(repo.path, "local")

    result = watch_repo(repo)

    assert result.action is WatchAction.LOCAL_AHEAD
    assert git(remote, "log", "--format=%s", "main") == "add a"


def test_two_way_repo_pushes_local_commits(tmp_path, remote):
    repo = make_repo(tmp_path, remote, WatchDirection.BOTH)
    watch_repo(repo)
    commit(repo.path, "local")

    assert watch_repo(repo).action is WatchAction.PUSHED
    assert git(remote, "log", "-1", "--format=%s", "main") == "add local"


def test_diverged_is_left_alone(tmp_path, remote, other):
    repo = make_repo(tmp_path, remote, WatchDirection.BOTH)
    watch_repo(repo)
    commit(repo.path, "local")
    push_from(other, "b")
    head = git(repo.path, "rev-parse", "HEAD")

    result = watch_repo(repo)

    assert result.action is WatchAction.DIVERGED
    assert result.action.needs_attention
    assert git(repo.path, "rev-parse", "HEAD") == head


def test_dirty_tree_is_skipped_but_reports_incoming(tmp_path, remote, other):
    repo = make_repo(tmp_path, remote)
    watch_repo(repo)
    (repo.path / "a").write_text("edited")
    push_from(other, "b")

    result = watch_repo(repo)

    assert result.action is WatchAction.SKIPPED_DIRTY
    assert len(result.commits) == 1
    assert not (repo.path / "b").exists()


def test_other_branch_is_skipped(tmp_path, remote, other):
    repo = make_repo(tmp_path, remote)
    watch_repo(repo)
    git(repo.path, "switch", "-qc", "feature")
    push_from(other, "b")

    result = watch_repo(repo)

    assert result.action is WatchAction.SKIPPED_BRANCH
    assert len(result.commits) == 1


def test_load_config_applies_defaults(tmp_path):
    base, elsewhere = tmp_path / "src", tmp_path / "elsewhere"
    config = tmp_path / "w.toml"
    config.write_text(
        f'owner = "me"\ndir = "{base}"\n'
        '[[repo]]\nname = "ideas"\n'
        f'[[repo]]\nname = "x"\nowner = "you"\npath = "{elsewhere}"\n'
        'branch = "dev"\ndirection = "both"\n'
    )

    ideas, x = load_watch_config(config)

    assert (ideas.path, ideas.clone_url) == (base / "ideas", "git@github.com:me/ideas.git")
    assert (ideas.branch, ideas.direction) == ("main", WatchDirection.PULL)
    assert (x.path, x.clone_url) == (elsewhere, "git@github.com:you/x.git")
    assert (x.branch, x.direction) == ("dev", WatchDirection.BOTH)


def test_load_config_requires_owner(tmp_path):
    config = tmp_path / "w.toml"
    config.write_text('[[repo]]\nname = "x"\n')
    with pytest.raises(ValueError, match="no owner"):
        load_watch_config(config)
