"""Tests for the automated release functionality."""

from pathlib import Path
from unittest.mock import patch

from gh_monitor.models import (
    ProjectType,
    ReleaseAction,
    ReleaseReport,
    ReleaseResult,
)
from gh_monitor.releaser import GitReleaser

CARGO_TOML = '[package]\nname = "demo"\nversion = "{v}"\n'
PYPROJECT_TOML = '[project]\nname = "demo"\nversion = "{v}"\n'
POETRY_TOML = '[tool.poetry]\nname = "demo"\nversion = "{v}"\n'


class TestReleaseModels:
    """Tests for release-related models."""

    def test_report_routes_each_action(self):
        report = ReleaseReport()
        report.add_result(ReleaseResult("a", ReleaseAction.RELEASED, "ok"))
        report.add_result(ReleaseResult("b", ReleaseAction.PLANNED, "plan"))
        report.add_result(ReleaseResult("c", ReleaseAction.CANCELLED, "no"))
        report.add_result(ReleaseResult("d", ReleaseAction.SKIPPED_ERROR, "boom"))
        report.add_result(ReleaseResult("e", ReleaseAction.SKIPPED_UNKNOWN_TYPE, "?"))
        report.add_result(ReleaseResult("f", ReleaseAction.SKIPPED_TOOL_MISSING, "no tool"))

        assert [r.repo_name for r in report.released] == ["a"]
        assert [r.repo_name for r in report.planned] == ["b"]
        assert [r.repo_name for r in report.cancelled] == ["c"]
        assert {r.repo_name for r in report.skipped} == {"d", "e", "f"}


class TestProjectDetection:
    """Tests for project type detection and version reading."""

    def _releaser(self) -> GitReleaser:
        return GitReleaser("owner")

    def test_cargo_takes_precedence_over_pyproject(self, tmp_path: Path):
        (tmp_path / "Cargo.toml").write_text(CARGO_TOML.format(v="1.0.0"))
        (tmp_path / "pyproject.toml").write_text(PYPROJECT_TOML.format(v="9.9.9"))
        assert self._releaser()._detect_type(tmp_path) == ProjectType.RUST

    def test_detects_python(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(PYPROJECT_TOML.format(v="1.0.0"))
        assert self._releaser()._detect_type(tmp_path) == ProjectType.PYTHON

    def test_detects_unknown(self, tmp_path: Path):
        assert self._releaser()._detect_type(tmp_path) == ProjectType.UNKNOWN

    def test_read_rust_version(self, tmp_path: Path):
        (tmp_path / "Cargo.toml").write_text(CARGO_TOML.format(v="2.3.4"))
        assert self._releaser()._read_version(tmp_path, ProjectType.RUST) == "2.3.4"

    def test_read_python_pep621_version(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(PYPROJECT_TOML.format(v="0.5.0"))
        assert self._releaser()._read_version(tmp_path, ProjectType.PYTHON) == "0.5.0"

    def test_read_poetry_version(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(POETRY_TOML.format(v="0.6.1"))
        assert self._releaser()._read_version(tmp_path, ProjectType.PYTHON) == "0.6.1"

    def test_read_virtual_workspace_version(self, tmp_path: Path):
        # Maturin-style: virtual root manifest, version lives in a member crate.
        (tmp_path / "Cargo.toml").write_text('[workspace]\nmembers = ["crates/*"]\n')
        crate = tmp_path / "crates" / "demo-core"
        crate.mkdir(parents=True)
        (crate / "Cargo.toml").write_text(CARGO_TOML.format(v="0.1.1"))
        assert self._releaser()._read_version(tmp_path, ProjectType.RUST) == "0.1.1"

    def test_read_workspace_inherited_version(self, tmp_path: Path):
        # Root crate inherits its version from [workspace.package].
        (tmp_path / "Cargo.toml").write_text(
            '[workspace.package]\nversion = "3.1.4"\n'
            '[package]\nname = "demo"\nversion.workspace = true\n'
        )
        assert self._releaser()._read_version(tmp_path, ProjectType.RUST) == "3.1.4"


class TestFindCandidates:
    """Tests for candidate selection."""

    def test_only_workflow_repos_with_untagged_commits(self):
        releaser = GitReleaser("owner")
        repos = [{"name": "ready"}, {"name": "no-workflow"}, {"name": "nothing-new"}]
        with (
            patch.object(releaser.collector, "get_repositories_for_sync", return_value=repos),
            patch.object(
                releaser.collector,
                "has_release_workflow",
                side_effect=lambda o, r: r != "no-workflow",
            ),
            patch.object(
                releaser.collector,
                "count_untagged_commits_on_main",
                side_effect=lambda o, r: 3 if r == "ready" else 0,
            ),
        ):
            candidates = releaser.find_candidates()

        assert [c["name"] for c in candidates] == ["ready"]

    def test_forks_are_excluded(self):
        releaser = GitReleaser("owner")
        repos = [{"name": "ours"}, {"name": "a-fork", "isFork": True}]
        with (
            patch.object(releaser.collector, "get_repositories_for_sync", return_value=repos),
            patch.object(releaser.collector, "has_release_workflow", return_value=True),
            patch.object(releaser.collector, "count_untagged_commits_on_main", return_value=3),
        ):
            candidates = releaser.find_candidates()

        assert [c["name"] for c in candidates] == ["ours"]

    def test_archived_repos_are_excluded(self):
        releaser = GitReleaser("owner")
        repos = [{"name": "ours"}, {"name": "abandoned", "isArchived": True}]
        with (
            patch.object(releaser.collector, "get_repositories_for_sync", return_value=repos),
            patch.object(releaser.collector, "has_release_workflow", return_value=True),
            patch.object(releaser.collector, "count_untagged_commits_on_main", return_value=3),
        ):
            candidates = releaser.find_candidates()

        assert [c["name"] for c in candidates] == ["ours"]


def _clone_writes_manifest(manifest: str, version: str):
    """Build a _run_git side effect whose clone creates a repo with a manifest."""

    def side_effect(args, cwd=None):
        if args[0] == "clone":
            repo_path = Path(args[2])
            repo_path.mkdir(parents=True, exist_ok=True)
            (repo_path / manifest).write_text(
                (CARGO_TOML if manifest == "Cargo.toml" else PYPROJECT_TOML).format(v=version)
            )
        return True, ""

    return side_effect


class TestReleaseRepo:
    """Tests for the per-repo release flow with mocked git/tooling."""

    def test_released_rust_repo(self):
        releaser = GitReleaser("owner", assume_yes=True)

        def bump(args, cwd):
            # Simulate `cargo set-version --bump minor` editing the manifest.
            (Path(cwd) / "Cargo.toml").write_text(CARGO_TOML.format(v="0.2.0"))
            return True, ""

        with (
            patch.object(
                releaser, "_run_git", side_effect=_clone_writes_manifest("Cargo.toml", "0.1.0")
            ),
            patch.object(releaser, "_run", side_effect=bump),
            patch("gh_monitor.releaser.shutil.which", return_value="/usr/bin/cargo"),
        ):
            result = releaser._release_repo("demo", "git@github.com:owner/demo.git")

        assert result.action == ReleaseAction.RELEASED
        assert result.project_type == ProjectType.RUST
        assert result.old_version == "0.1.0"
        assert result.new_version == "0.2.0"
        assert result.tag == "v0.2.0"

    def test_rust_falls_back_to_cargo_release(self):
        releaser = GitReleaser("owner", assume_yes=True)
        ran = []

        def bump(args, cwd):
            ran.append(args)
            (Path(cwd) / "Cargo.toml").write_text(CARGO_TOML.format(v="0.1.1"))
            return True, ""

        # cargo-edit absent, cargo-release present.
        def which(name):
            return "/usr/bin/cargo-release" if name == "cargo-release" else None

        with (
            patch.object(
                releaser, "_run_git", side_effect=_clone_writes_manifest("Cargo.toml", "0.1.0")
            ),
            patch.object(releaser, "_run", side_effect=bump),
            patch("gh_monitor.releaser.shutil.which", side_effect=which),
        ):
            result = releaser._release_repo("demo", "url")

        assert result.action == ReleaseAction.RELEASED
        assert result.tag == "v0.1.1"
        # Default level is patch.
        assert ran == [["cargo", "release", "version", "patch", "--execute", "--no-confirm"]]

    def test_level_threads_into_bump_command(self):
        releaser = GitReleaser("owner", level="minor", assume_yes=True)
        ran = []

        def bump(args, cwd):
            ran.append(args)
            (Path(cwd) / "pyproject.toml").write_text(PYPROJECT_TOML.format(v="0.2.0"))
            return True, ""

        with (
            patch.object(
                releaser, "_run_git", side_effect=_clone_writes_manifest("pyproject.toml", "0.1.0")
            ),
            patch.object(releaser, "_run", side_effect=bump),
            patch("gh_monitor.releaser.shutil.which", return_value="/usr/bin/uv"),
        ):
            result = releaser._release_repo("demo", "url")

        assert result.tag == "v0.2.0"
        assert ran == [["uv", "version", "--bump", "minor"]]

    def test_dry_run_does_not_push(self):
        releaser = GitReleaser("owner", dry_run=True)

        def bump(args, cwd):
            (Path(cwd) / "pyproject.toml").write_text(PYPROJECT_TOML.format(v="1.1.0"))
            return True, ""

        with (
            patch.object(
                releaser, "_run_git", side_effect=_clone_writes_manifest("pyproject.toml", "1.0.0")
            ) as mock_git,
            patch.object(releaser, "_run", side_effect=bump),
            patch("gh_monitor.releaser.shutil.which", return_value="/usr/bin/uv"),
        ):
            result = releaser._release_repo("demo", "url")

        assert result.action == ReleaseAction.PLANNED
        assert result.new_version == "1.1.0"
        assert result.tag == "v1.1.0"
        # Only the clone ran — no commit/tag/push.
        assert [call.args[0][0] for call in mock_git.call_args_list] == ["clone"]

    def test_skips_unknown_type(self):
        releaser = GitReleaser("owner", assume_yes=True)

        def clone_empty(args, cwd=None):
            if args[0] == "clone":
                Path(args[2]).mkdir(parents=True, exist_ok=True)
            return True, ""

        with patch.object(releaser, "_run_git", side_effect=clone_empty):
            result = releaser._release_repo("demo", "url")

        assert result.action == ReleaseAction.SKIPPED_UNKNOWN_TYPE

    def test_skips_when_tool_missing(self):
        releaser = GitReleaser("owner", assume_yes=True)

        with (
            patch.object(
                releaser, "_run_git", side_effect=_clone_writes_manifest("Cargo.toml", "0.1.0")
            ),
            patch("gh_monitor.releaser.shutil.which", return_value=None),
        ):
            result = releaser._release_repo("demo", "url")

        assert result.action == ReleaseAction.SKIPPED_TOOL_MISSING
        assert result.project_type == ProjectType.RUST

    def test_cancelled_when_confirm_declined(self):
        releaser = GitReleaser("owner", confirm_callback=lambda r: False)

        def bump(args, cwd):
            (Path(cwd) / "Cargo.toml").write_text(CARGO_TOML.format(v="0.2.0"))
            return True, ""

        with (
            patch.object(
                releaser, "_run_git", side_effect=_clone_writes_manifest("Cargo.toml", "0.1.0")
            ),
            patch.object(releaser, "_run", side_effect=bump),
            patch("gh_monitor.releaser.shutil.which", return_value="/usr/bin/cargo"),
        ):
            result = releaser._release_repo("demo", "url")

        assert result.action == ReleaseAction.CANCELLED


class TestReleaseAll:
    """Tests for the release_all orchestration."""

    def test_filters_to_single_repo(self):
        releaser = GitReleaser("owner")
        candidates = [{"name": "a", "sshUrl": "a-url"}, {"name": "b", "sshUrl": "b-url"}]

        with (
            patch.object(releaser, "find_candidates", return_value=candidates),
            patch.object(
                releaser,
                "_release_repo",
                side_effect=lambda name, url: ReleaseResult(name, ReleaseAction.RELEASED, "ok"),
            ) as mock_release,
        ):
            report = releaser.release_all(repo_filter="b")

        assert [r.repo_name for r in report.released] == ["b"]
        mock_release.assert_called_once_with("b", "b-url")

    def test_empty_when_no_candidates(self):
        releaser = GitReleaser("owner")
        with patch.object(releaser, "find_candidates", return_value=[]):
            report = releaser.release_all()
        assert report.released == [] and report.skipped == []
