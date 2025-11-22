"""Git repository synchronization with local filesystem."""

import subprocess
from pathlib import Path
from typing import Callable

from .collector import GitHubCollector
from .models import SyncAction, SyncReport, SyncResult


class GitSyncer:
    """Syncs GitHub repositories with a local directory."""

    def __init__(self, owner: str, git_dir: Path, verbose: bool = False):
        """Initialize syncer.

        Args:
            owner: GitHub organization or user to sync
            git_dir: Local directory to sync repos to (e.g., ~/git)
            verbose: Enable verbose output
        """
        self.owner = owner
        self.git_dir = git_dir.expanduser().resolve()
        self.verbose = verbose
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

    def _is_git_clean(self, repo_path: Path) -> bool:
        """Check if a git repo has no uncommitted changes."""
        success, output = self._run_git(["status", "--porcelain"], cwd=repo_path)
        return success and not output

    def _get_current_branch(self, repo_path: Path) -> str | None:
        """Get the current branch name."""
        success, output = self._run_git(
            ["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path
        )
        return output if success else None

    def _needs_pull(self, repo_path: Path) -> bool:
        """Check if repo is behind remote (needs pull)."""
        # Fetch to update remote refs
        self._run_git(["fetch"], cwd=repo_path)

        # Check if we're behind
        success, output = self._run_git(
            ["rev-list", "--count", "HEAD..@{upstream}"], cwd=repo_path
        )
        if success:
            try:
                return int(output) > 0
            except ValueError:
                return False
        return False

    def _clone_repo(self, repo_name: str, clone_url: str) -> SyncResult:
        """Clone a repository."""
        repo_path = self.git_dir / repo_name
        success, output = self._run_git(["clone", clone_url, str(repo_path)])

        if success:
            return SyncResult(
                repo_name=repo_name,
                action=SyncAction.CLONED,
                message=f"Cloned to {repo_path}",
            )
        else:
            return SyncResult(
                repo_name=repo_name,
                action=SyncAction.SKIPPED_ERROR,
                message=f"Clone failed: {output}",
            )

    def _pull_repo(self, repo_name: str, repo_path: Path) -> SyncResult:
        """Pull latest changes for a repository."""
        branch = self._get_current_branch(repo_path)

        # Check if clean
        if not self._is_git_clean(repo_path):
            return SyncResult(
                repo_name=repo_name,
                action=SyncAction.SKIPPED_DIRTY,
                message="Uncommitted changes present",
                branch=branch,
            )

        # Check if needs pull
        if not self._needs_pull(repo_path):
            return SyncResult(
                repo_name=repo_name,
                action=SyncAction.ALREADY_CURRENT,
                message="Already up to date",
                branch=branch,
            )

        # Try to pull
        success, output = self._run_git(["pull"], cwd=repo_path)

        if success:
            return SyncResult(
                repo_name=repo_name,
                action=SyncAction.PULLED,
                message="Updated successfully",
                branch=branch,
            )
        else:
            return SyncResult(
                repo_name=repo_name,
                action=SyncAction.SKIPPED_ERROR,
                message=f"Pull failed: {output}",
                branch=branch,
            )

    def sync_all(
        self, progress_callback: Callable[[int], None] | None = None
    ) -> SyncReport:
        """Sync all repositories.

        Args:
            progress_callback: Optional callback for progress updates (0-100)

        Returns:
            SyncReport with summary of actions taken
        """
        # Ensure git directory exists
        self.git_dir.mkdir(parents=True, exist_ok=True)

        # Get list of repos from GitHub (all repos, no date filter)
        repos = self.collector._run_gh([
            "repo",
            "list",
            self.owner,
            "--json",
            "name,url,sshUrl",
            "--limit",
            "1000",
        ])

        if not repos:
            return SyncReport()

        report = SyncReport()
        total = len(repos)

        for i, repo in enumerate(repos):
            repo_name = repo["name"]
            repo_path = self.git_dir / repo_name
            # Prefer SSH URL for cloning
            clone_url = repo.get("sshUrl") or repo.get("url")

            if repo_path.exists() and (repo_path / ".git").exists():
                # Existing repo - try to pull
                result = self._pull_repo(repo_name, repo_path)
            else:
                # Missing repo - clone it
                result = self._clone_repo(repo_name, clone_url)

            report.add_result(result)

            if progress_callback:
                progress_callback(int((i + 1) / total * 100))

        return report
