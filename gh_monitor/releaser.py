"""Automated version releases for repos with a release workflow.

The bump level defaults to ``patch`` and can be set to ``minor`` or ``major``.
For each candidate repository (one that has a ``.github/workflows/release.yml``
and untagged commits on ``main``) this:

1. Clones the repo into a throwaway temp directory.
2. Detects the project type (``Cargo.toml`` takes precedence over
   ``pyproject.toml`` since some Rust repos also ship a ``pyproject.toml``).
3. Bumps the version with the language's own tool — Python
   ``uv version --bump <level>``; Rust ``cargo set-version --bump <level>``
   (cargo-edit), falling back to ``cargo release version <level>``
   (cargo-release) when cargo-edit is not installed. Each tool only edits the
   manifest; commit, tag and push are handled here so both ecosystems behave
   identically.
4. Commits the bump, tags ``vX.Y.Z`` and pushes, which triggers the release
   workflow (it runs on tag push).

Nothing is written when ``dry_run`` is set: the bump is computed in the temp
clone to preview the exact new version, then discarded.
"""

import shutil
import subprocess
import tempfile
import tomllib
from collections.abc import Callable
from pathlib import Path

from .collector import GitHubCollector
from .models import ProjectType, ReleaseAction, ReleaseReport, ReleaseResult

# Project type -> manifest filename whose version is bumped.
_MANIFESTS: dict[ProjectType, str] = {
    ProjectType.RUST: "Cargo.toml",
    ProjectType.PYTHON: "pyproject.toml",
}


class GitReleaser:
    """Publishes version releases across an owner's repositories."""

    def __init__(
        self,
        owner: str,
        verbose: bool = False,
        days: int = 90,
        level: str = "patch",
        dry_run: bool = False,
        assume_yes: bool = False,
        confirm_callback: Callable[[ReleaseResult], bool] | None = None,
    ):
        """Initialize the releaser.

        Args:
            owner: GitHub organization or user.
            verbose: Enable verbose output.
            days: Only consider repos modified in the last N days.
            level: Semver bump level to apply (patch, minor, or major).
            dry_run: Compute and preview bumps without writing or pushing.
            assume_yes: Skip the per-repo confirmation prompt.
            confirm_callback: Called with a planned ReleaseResult; return True to
                proceed with the push. Ignored when dry_run or assume_yes.
        """
        self.owner = owner
        self.verbose = verbose
        self.days = days
        self.level = level
        self.dry_run = dry_run
        self.assume_yes = assume_yes
        self.confirm_callback = confirm_callback
        self.collector = GitHubCollector(verbose=verbose)

    def _run_git(self, args: list[str], cwd: Path | None = None) -> tuple[bool, str]:
        """Run a git command and return (success, output)."""
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=cwd,
            check=False,
        )
        output = result.stdout.strip() or result.stderr.strip()
        return result.returncode == 0, output

    def _run(self, args: list[str], cwd: Path) -> tuple[bool, str]:
        """Run an arbitrary command and return (success, output)."""
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=cwd,
            check=False,
        )
        output = result.stdout.strip() or result.stderr.strip()
        return result.returncode == 0, output

    def _detect_type(self, repo_path: Path) -> ProjectType:
        """Detect the project type; Cargo.toml wins over pyproject.toml."""
        if (repo_path / "Cargo.toml").exists():
            return ProjectType.RUST
        if (repo_path / "pyproject.toml").exists():
            return ProjectType.PYTHON
        return ProjectType.UNKNOWN

    def _resolve_bump_cmd(self, project_type: ProjectType) -> list[str] | None:
        """Pick the version-bump command for the project, or None if no tool.

        Each command only edits the manifest (commit/tag/push is handled here).
        For Rust, cargo-edit's ``set-version`` is preferred, falling back to
        cargo-release's ``release version`` subcommand when cargo-edit is absent.
        """
        if project_type == ProjectType.PYTHON:
            if shutil.which("uv"):
                return ["uv", "version", "--bump", self.level]
            return None
        if project_type == ProjectType.RUST:
            if shutil.which("cargo-set-version"):
                return ["cargo", "set-version", "--bump", self.level]
            if shutil.which("cargo-release"):
                return ["cargo", "release", "version", self.level, "--execute", "--no-confirm"]
            return None
        return None

    def _read_version(self, repo_path: Path, project_type: ProjectType) -> str | None:
        """Read the current version from the project manifest."""
        manifest = _MANIFESTS[project_type]
        try:
            data = tomllib.loads((repo_path / manifest).read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return None
        if project_type == ProjectType.RUST:
            return data.get("package", {}).get("version")
        # Python: PEP 621 [project] or Poetry [tool.poetry]
        project_version = data.get("project", {}).get("version")
        poetry_version = data.get("tool", {}).get("poetry", {}).get("version")
        return project_version or poetry_version

    def _release_repo(self, repo_name: str, clone_url: str) -> ReleaseResult:
        """Clone, bump, and (unless dry-run) commit/tag/push a single repo."""
        with tempfile.TemporaryDirectory(prefix="gh-monitor-release-") as tmp:
            repo_path = Path(tmp) / repo_name

            ok, out = self._run_git(["clone", clone_url, str(repo_path)])
            if not ok:
                return ReleaseResult(
                    repo_name=repo_name,
                    action=ReleaseAction.SKIPPED_ERROR,
                    message=f"Clone failed: {out}",
                )

            project_type = self._detect_type(repo_path)
            if project_type == ProjectType.UNKNOWN:
                return ReleaseResult(
                    repo_name=repo_name,
                    action=ReleaseAction.SKIPPED_UNKNOWN_TYPE,
                    message="No Cargo.toml or pyproject.toml found",
                )

            bump_cmd = self._resolve_bump_cmd(project_type)
            if bump_cmd is None:
                tool = "cargo-edit or cargo-release" if project_type == ProjectType.RUST else "uv"
                return ReleaseResult(
                    repo_name=repo_name,
                    action=ReleaseAction.SKIPPED_TOOL_MISSING,
                    message=f"{tool} not installed",
                    project_type=project_type,
                )

            old_version = self._read_version(repo_path, project_type)

            ok, out = self._run(bump_cmd, cwd=repo_path)
            if not ok:
                return ReleaseResult(
                    repo_name=repo_name,
                    action=ReleaseAction.SKIPPED_ERROR,
                    message=f"Version bump failed: {out}",
                    project_type=project_type,
                    old_version=old_version,
                )

            new_version = self._read_version(repo_path, project_type)
            if not new_version:
                return ReleaseResult(
                    repo_name=repo_name,
                    action=ReleaseAction.SKIPPED_ERROR,
                    message="Could not read version after bump",
                    project_type=project_type,
                    old_version=old_version,
                )

            tag = f"v{new_version}"
            planned = ReleaseResult(
                repo_name=repo_name,
                action=ReleaseAction.PLANNED,
                message=f"{old_version} -> {new_version}",
                project_type=project_type,
                old_version=old_version,
                new_version=new_version,
                tag=tag,
            )

            if self.dry_run:
                return planned

            if not self.assume_yes and self.confirm_callback and not self.confirm_callback(planned):
                return ReleaseResult(
                    repo_name=repo_name,
                    action=ReleaseAction.CANCELLED,
                    message="Cancelled by user",
                    project_type=project_type,
                    old_version=old_version,
                    new_version=new_version,
                    tag=tag,
                )

            return self._commit_tag_push(repo_path, planned)

    def _commit_tag_push(self, repo_path: Path, planned: ReleaseResult) -> ReleaseResult:
        """Commit the bump, create the tag, and push commit + tag."""
        steps = [
            (["commit", "-am", f"Release {planned.tag}"], "commit"),
            (["tag", planned.tag], "tag"),
            (["push", "origin", "HEAD"], "push"),
            (["push", "origin", planned.tag], "push tag"),
        ]
        for args, label in steps:
            ok, out = self._run_git(args, cwd=repo_path)
            if not ok:
                return ReleaseResult(
                    repo_name=planned.repo_name,
                    action=ReleaseAction.SKIPPED_ERROR,
                    message=f"git {label} failed: {out}",
                    project_type=planned.project_type,
                    old_version=planned.old_version,
                    new_version=planned.new_version,
                    tag=planned.tag,
                )
        return ReleaseResult(
            repo_name=planned.repo_name,
            action=ReleaseAction.RELEASED,
            message=f"Released {planned.tag}",
            project_type=planned.project_type,
            old_version=planned.old_version,
            new_version=planned.new_version,
            tag=planned.tag,
        )

    def find_candidates(self) -> list[dict]:
        """Repos with a release workflow and untagged commits on main.

        Forks are never released — we only publish our own projects, not
        clones of someone else's repo that happen to live under the owner.
        """
        repos = self.collector.get_repositories_for_sync(self.owner, self.days)
        candidates = []
        for repo in repos:
            name = repo["name"]
            if repo.get("isFork"):
                continue
            if not self.collector.has_release_workflow(self.owner, name):
                continue
            if self.collector.count_untagged_commits_on_main(self.owner, name) > 0:
                candidates.append(repo)
        return candidates

    def release_all(
        self,
        repo_filter: str | None = None,
        progress_callback: Callable[[int], None] | None = None,
    ) -> ReleaseReport:
        """Release all candidate repos (optionally a single named repo).

        Args:
            repo_filter: If set, only release the repo with this exact name.
            progress_callback: Optional callback for progress updates (0-100).

        Returns:
            ReleaseReport summarizing released/planned/skipped/cancelled repos.
        """
        candidates = self.find_candidates()
        if repo_filter:
            candidates = [r for r in candidates if r["name"] == repo_filter]

        report = ReleaseReport()
        total = len(candidates)
        if total == 0:
            return report

        for i, repo in enumerate(candidates):
            clone_url = repo.get("sshUrl") or repo.get("url")
            report.add_result(self._release_repo(repo["name"], clone_url))
            if progress_callback:
                progress_callback(int((i + 1) / total * 100))

        return report
