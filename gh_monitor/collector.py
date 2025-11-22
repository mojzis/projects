"""GitHub CLI interaction for data collection."""

import json
import subprocess
from datetime import UTC, datetime, timedelta
from typing import Any


class GitHubCLIError(Exception):
    """Raised when GitHub CLI command fails."""


class GitHubCollector:
    """Handles all interactions with GitHub CLI."""

    def __init__(self, verbose: bool = False):
        """Initialize collector with optional verbose output."""
        self.verbose = verbose

    def _run_gh(self, args: list[str]) -> dict[str, Any] | list[Any]:
        """Execute gh CLI command with error handling."""
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        if result.returncode != 0:
            raise GitHubCLIError(f"gh command failed: {result.stderr}")

        return json.loads(result.stdout) if result.stdout.strip() else {}

    def get_repositories(self, owner: str, since_days: int = 30) -> list[dict]:
        """Get repositories modified in the last N days."""
        repos = self._run_gh(
            [
                "repo",
                "list",
                owner,
                "--json",
                "name,pushedAt,updatedAt,stargazerCount,forkCount,url",
                "--limit",
                "1000",
            ]
        )

        # Filter by date
        cutoff = datetime.now(UTC) - timedelta(days=since_days)
        filtered = []

        for repo in repos:
            pushed_at = datetime.fromisoformat(repo["pushedAt"].replace("Z", "+00:00"))
            if pushed_at > cutoff:
                filtered.append(repo)

        return filtered

    def get_last_commit(self, owner: str, repo: str) -> dict | None:
        """Get last commit on main branch."""
        try:
            commit = self._run_gh(["api", f"repos/{owner}/{repo}/commits/main"])
            return commit
        except GitHubCLIError:
            # Try master branch if main fails
            try:
                commit = self._run_gh(["api", f"repos/{owner}/{repo}/commits/master"])
                return commit
            except GitHubCLIError:
                return None

    def get_open_prs(self, owner: str, repo: str) -> list[dict]:
        """Get all open pull requests."""
        try:
            prs = self._run_gh(
                [
                    "pr",
                    "list",
                    "--repo",
                    f"{owner}/{repo}",
                    "--state",
                    "open",
                    "--json",
                    "number,title,createdAt,author,url",
                    "--limit",
                    "100",
                ]
            )
            return prs if isinstance(prs, list) else []
        except GitHubCLIError:
            return []

    def get_branches(self, owner: str, repo: str) -> list[str]:
        """Get all branch names."""
        try:
            branches = self._run_gh(["api", f"repos/{owner}/{repo}/branches", "--paginate"])
            return [b["name"] for b in branches] if isinstance(branches, list) else []
        except GitHubCLIError:
            return []

    def get_pr_branches(self, owner: str, repo: str) -> set[str]:
        """Get all branches that have PRs (open or closed)."""
        try:
            prs = self._run_gh(
                [
                    "pr",
                    "list",
                    "--repo",
                    f"{owner}/{repo}",
                    "--state",
                    "all",
                    "--json",
                    "headRefName",
                    "--limit",
                    "1000",
                ]
            )
            return {pr["headRefName"] for pr in prs} if isinstance(prs, list) else set()
        except GitHubCLIError:
            return set()

    def get_github_pages(self, owner: str, repo: str) -> dict | None:
        """Get GitHub Pages status."""
        try:
            pages = self._run_gh(["api", f"repos/{owner}/{repo}/pages"])
            return pages if isinstance(pages, dict) else None
        except GitHubCLIError:
            return None

    def get_ci_runs(self, owner: str, repo: str, limit: int = 20) -> list[dict]:
        """Get recent CI/CD runs."""
        try:
            runs = self._run_gh(
                [
                    "run",
                    "list",
                    "--repo",
                    f"{owner}/{repo}",
                    "--limit",
                    str(limit),
                    "--json",
                    "status,conclusion,name,createdAt",
                ]
            )
            return runs if isinstance(runs, list) else []
        except GitHubCLIError:
            return []

    def get_repo_details(self, owner: str, repo: str) -> dict:
        """Get repository details (stars, forks, language, issues)."""
        try:
            details = self._run_gh(
                [
                    "repo",
                    "view",
                    f"{owner}/{repo}",
                    "--json",
                    "stargazerCount,forkCount,openIssues,primaryLanguage",
                ]
            )
            return details if isinstance(details, dict) else {}
        except GitHubCLIError:
            return {}

    def get_repositories_for_sync(self, owner: str, since_days: int | None = None) -> list[dict]:
        """Get repositories for syncing, optionally filtered by activity.

        Args:
            owner: GitHub organization or user
            since_days: If provided, only return repos modified in the last N days.
                       If None, return all repos.

        Returns:
            List of repo dicts with name, url, sshUrl fields
        """
        repos = self._run_gh(
            [
                "repo",
                "list",
                owner,
                "--json",
                "name,url,sshUrl,pushedAt",
                "--limit",
                "1000",
            ]
        )

        if not repos:
            return []

        # Filter by date if since_days is specified
        if since_days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=since_days)
            filtered = []
            for repo in repos:
                pushed_at = datetime.fromisoformat(repo["pushedAt"].replace("Z", "+00:00"))
                if pushed_at > cutoff:
                    filtered.append(repo)
            return filtered

        return repos
