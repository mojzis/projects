"""Main orchestration logic for GitHub project monitoring."""

from datetime import datetime, timezone
from typing import Callable

from .collector import GitHubCollector
from .models import CIRun, CIStatus, Commit, PullRequest, Repository


class ProjectMonitor:
    """Orchestrates data collection across multiple repositories."""

    def __init__(self, owner: str, days: int = 30, verbose: bool = False):
        """Initialize monitor for a GitHub owner."""
        self.owner = owner
        self.days = days
        self.verbose = verbose
        self.collector = GitHubCollector(verbose)

    def collect_all_data(
        self, progress_callback: Callable[[int], None] | None = None
    ) -> list[Repository]:
        """Collect data for all repositories."""
        # Get repositories
        repos = self.collector.get_repositories(self.owner, self.days)
        total = len(repos)

        if total == 0:
            return []

        repositories = []
        for idx, repo_info in enumerate(repos):
            repo_name = repo_info["name"]

            if self.verbose:
                print(f"Processing {self.owner}/{repo_name}...")

            # Collect all data for this repository
            repo = self._collect_repo_data(repo_name, repo_info)
            repositories.append(repo)

            # Update progress
            if progress_callback:
                progress_callback(int((idx + 1) / total * 100))

        return repositories

    def _collect_repo_data(self, repo_name: str, repo_info: dict) -> Repository:
        """Collect all data for a single repository."""
        # Get last commit
        last_commit = self._get_last_commit(repo_name)

        # Get open PRs
        open_prs = self._get_open_prs(repo_name)

        # Get branches without PRs
        branches_without_prs = self._get_branches_without_prs(repo_name)

        # Get GitHub Pages info
        pages_enabled, pages_url = self._get_github_pages(repo_name)

        # Get CI status and runs
        ci_status, ci_runs, ci_success_rate = self._get_ci_info(repo_name)

        # Get repository details
        details = self.collector.get_repo_details(self.owner, repo_name)

        return Repository(
            name=repo_name,
            owner=self.owner,
            full_name=f"{self.owner}/{repo_name}",
            url=repo_info.get("url", f"https://github.com/{self.owner}/{repo_name}"),
            last_commit=last_commit,
            open_prs=open_prs,
            branches_without_prs=branches_without_prs,
            github_pages_enabled=pages_enabled,
            github_pages_url=pages_url,
            ci_status=ci_status,
            ci_recent_runs=ci_runs,
            ci_success_rate=ci_success_rate,
            last_updated=datetime.now(timezone.utc),
            stars=details.get("stargazerCount", 0),
            forks=details.get("forkCount", 0),
            open_issues=details.get("openIssues", {}).get("totalCount", 0),
            primary_language=details.get("primaryLanguage", {}).get("name")
            if details.get("primaryLanguage")
            else None,
        )

    def _get_last_commit(self, repo_name: str) -> Commit | None:
        """Get last commit on main/master branch."""
        commit_data = self.collector.get_last_commit(self.owner, repo_name)
        if not commit_data:
            return None

        commit_info = commit_data.get("commit", {})
        author_info = commit_info.get("author", {})

        return Commit(
            sha=commit_data.get("sha", ""),
            message=commit_info.get("message", "").split("\n")[0],  # First line only
            author=author_info.get("name", "Unknown"),
            date=datetime.fromisoformat(
                author_info.get("date", datetime.now(timezone.utc).isoformat()).replace(
                    "Z", "+00:00"
                )
            ),
        )

    def _get_open_prs(self, repo_name: str) -> list[PullRequest]:
        """Get all open pull requests with age calculation."""
        prs_data = self.collector.get_open_prs(self.owner, repo_name)
        prs = []

        for pr in prs_data:
            created_at = datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - created_at).days

            prs.append(
                PullRequest(
                    number=pr["number"],
                    title=pr["title"],
                    created_at=created_at,
                    author=pr.get("author", {}).get("login", "Unknown"),
                    age_days=age_days,
                    url=pr["url"],
                )
            )

        return prs

    def _get_branches_without_prs(self, repo_name: str) -> list[str]:
        """Get branches that don't have associated PRs."""
        all_branches = self.collector.get_branches(self.owner, repo_name)
        pr_branches = self.collector.get_pr_branches(self.owner, repo_name)

        # Filter out main/master and branches with PRs
        return [
            b
            for b in all_branches
            if b not in {"main", "master"} and b not in pr_branches
        ]

    def _get_github_pages(self, repo_name: str) -> tuple[bool, str | None]:
        """Get GitHub Pages status and URL."""
        pages = self.collector.get_github_pages(self.owner, repo_name)
        if not pages:
            return False, None

        return True, pages.get("html_url")

    def _get_ci_info(self, repo_name: str) -> tuple[CIStatus, list[CIRun], float]:
        """Get CI status, recent runs, and success rate."""
        runs_data = self.collector.get_ci_runs(self.owner, repo_name)

        if not runs_data:
            return CIStatus.NO_CI, [], 0.0

        # Convert to CIRun objects
        ci_runs = []
        for run in runs_data:
            ci_runs.append(
                CIRun(
                    name=run.get("name", "Unknown"),
                    status=run.get("status", "unknown"),
                    conclusion=run.get("conclusion"),
                    created_at=datetime.fromisoformat(
                        run.get("createdAt", datetime.now(timezone.utc).isoformat()).replace(
                            "Z", "+00:00"
                        )
                    ),
                )
            )

        # Calculate success rate
        completed_runs = [r for r in ci_runs if r.conclusion is not None]
        if not completed_runs:
            ci_status = CIStatus.PENDING
            success_rate = 0.0
        else:
            successful = sum(1 for r in completed_runs if r.conclusion == "success")
            success_rate = successful / len(completed_runs)

            # Determine overall status based on most recent run
            latest_conclusion = ci_runs[0].conclusion if ci_runs else None
            if latest_conclusion == "success":
                ci_status = CIStatus.SUCCESS
            elif latest_conclusion == "failure":
                ci_status = CIStatus.FAILURE
            elif latest_conclusion is None:
                ci_status = CIStatus.PENDING
            else:
                ci_status = CIStatus.UNKNOWN

        return ci_status, ci_runs, success_rate
