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
   (cargo-release) when cargo-edit is not installed. A Rust repo with a
   ``release.toml`` always uses cargo-release and also runs its ``replace``
   step, so the ``pre-release-replacements`` there (doc version pins, etc.) are
   applied — cargo-edit knows nothing about them. The tools only edit files;
   commit, tag and push are handled here so both ecosystems behave identically.
4. Commits the bump, tags ``vX.Y.Z`` and pushes, which triggers the release
   workflow (it runs on tag push).

Nothing is written when ``dry_run`` is set: the bump is computed in the temp
clone to preview the exact new version, then discarded.
"""

import shutil
import tempfile
import tomllib
from collections.abc import Callable
from pathlib import Path

from .collector import GitHubCollector
from .models import ProjectType, ReleaseAction, ReleaseReport, ReleaseResult
from .process import run_command

# Project type -> manifest filename whose version is bumped.
_MANIFESTS: dict[ProjectType, str] = {
    ProjectType.RUST: "Cargo.toml",
    ProjectType.PYTHON: "pyproject.toml",
}

# Make cargo-release edit files without prompting (it is a dry run otherwise).
_CARGO_RELEASE_FLAGS = ["--execute", "--no-confirm"]


def _missing_tool(project_type: ProjectType, repo_path: Path) -> str:
    """Name the bump tool a repo needs, for the tool-missing skip message."""
    if project_type == ProjectType.PYTHON:
        return "uv"
    if (repo_path / "release.toml").exists():
        return "cargo-release (required by release.toml)"
    return "cargo-edit or cargo-release"


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
        return run_command(["git", *args], cwd=cwd)

    def _run(self, args: list[str], cwd: Path) -> tuple[bool, str]:
        """Run an arbitrary command and return (success, output)."""
        return run_command(args, cwd=cwd)

    def _run_all(self, cmds: list[list[str]], cwd: Path) -> tuple[bool, str]:
        """Run commands in order, stopping at the first failure."""
        ok, out = True, ""
        for cmd in cmds:
            ok, out = self._run(cmd, cwd=cwd)
            if not ok:
                break
        return ok, out

    def _detect_type(self, repo_path: Path) -> ProjectType:
        """Detect the project type; Cargo.toml wins over pyproject.toml."""
        if (repo_path / "Cargo.toml").exists():
            return ProjectType.RUST
        if (repo_path / "pyproject.toml").exists():
            return ProjectType.PYTHON
        return ProjectType.UNKNOWN

    def _resolve_bump_cmds(
        self, project_type: ProjectType, repo_path: Path
    ) -> list[list[str]] | None:
        """Pick the version-bump commands for the project, or None if no tool.

        The commands only edit files (commit/tag/push is handled here). For
        Rust, cargo-edit's ``set-version`` is preferred, falling back to
        cargo-release's ``release version`` subcommand when cargo-edit is absent.
        A repo with a ``release.toml`` requires cargo-release: its ``replace``
        step applies the ``pre-release-replacements`` configured there.
        """
        if project_type == ProjectType.PYTHON:
            if shutil.which("uv"):
                return [["uv", "version", "--bump", self.level]]
            return None
        if project_type == ProjectType.RUST:
            release_version = ["cargo", "release", "version", self.level, *_CARGO_RELEASE_FLAGS]
            if (repo_path / "release.toml").exists():
                if shutil.which("cargo-release"):
                    return [release_version, ["cargo", "release", "replace", *_CARGO_RELEASE_FLAGS]]
                return None
            if shutil.which("cargo-set-version"):
                return [["cargo", "set-version", "--bump", self.level]]
            if shutil.which("cargo-release"):
                return [release_version]
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
            return self._read_rust_version(repo_path, data)
        # Python: PEP 621 [project] or Poetry [tool.poetry]
        project_version = data.get("project", {}).get("version")
        poetry_version = data.get("tool", {}).get("poetry", {}).get("version")
        return project_version or poetry_version

    @staticmethod
    def _crate_version(manifest: dict, root: dict) -> str | None:
        """Version of a single crate, resolving ``version.workspace = true``."""
        version = manifest.get("package", {}).get("version")
        if isinstance(version, str):
            return version
        if isinstance(version, dict) and version.get("workspace"):
            # Inherited from the workspace root's [workspace.package].
            return root.get("workspace", {}).get("package", {}).get("version")
        return None

    def _read_rust_version(self, repo_path: Path, root: dict) -> str | None:
        """Read a crate version, following workspace inheritance.

        Handles three layouts:
        - a plain single-crate ``[package].version`` string;
        - ``version.workspace = true`` inherited from ``[workspace.package]``;
        - a *virtual* workspace (no ``[package]`` at the root, e.g. maturin
          projects) whose version lives in a member crate under ``crates/*``.
          The bump tool touches every member, so any member's version works.
        """
        version = self._crate_version(root, root)
        if version:
            return version
        for member in root.get("workspace", {}).get("members", []):
            for member_dir in sorted(repo_path.glob(member)):
                manifest = member_dir / "Cargo.toml"
                if not manifest.is_file():
                    continue
                try:
                    data = tomllib.loads(manifest.read_text(encoding="utf-8"))
                except (OSError, tomllib.TOMLDecodeError):
                    continue
                version = self._crate_version(data, root)
                if version:
                    return version
        return None

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

            bump_cmds = self._resolve_bump_cmds(project_type, repo_path)
            if bump_cmds is None:
                return ReleaseResult(
                    repo_name=repo_name,
                    action=ReleaseAction.SKIPPED_TOOL_MISSING,
                    message=f"{_missing_tool(project_type, repo_path)} not installed",
                    project_type=project_type,
                )

            old_version = self._read_version(repo_path, project_type)

            ok, out = self._run_all(bump_cmds, cwd=repo_path)
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

            return self._commit_tag_push(repo_path, planned, tag)

    def _commit_tag_push(self, repo_path: Path, planned: ReleaseResult, tag: str) -> ReleaseResult:
        """Commit the bump, create the tag, and push commit + tag."""
        steps = [
            (["commit", "-am", f"Release {tag}"], "commit"),
            (["tag", tag], "tag"),
            (["push", "origin", "HEAD"], "push"),
            (["push", "origin", tag], "push tag"),
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
        Archived repos are abandoned and skipped too.
        """
        repos = self.collector.get_repositories_for_sync(self.owner, self.days)
        candidates = []
        for repo in repos:
            name = repo["name"]
            if repo.get("isFork") or repo.get("isArchived"):
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
            clone_url = repo.get("sshUrl") or repo["url"]
            report.add_result(self._release_repo(repo["name"], clone_url))
            if progress_callback:
                progress_callback(int((i + 1) / total * 100))

        return report
