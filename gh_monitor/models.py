"""Data models for GitHub project monitoring."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class CIStatus(Enum):
    """CI pipeline status."""

    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    NO_CI = "no_ci"
    UNKNOWN = "unknown"


@dataclass
class Commit:
    """Represents a git commit."""

    sha: str
    message: str
    author: str
    date: datetime

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "sha": self.sha,
            "message": self.message,
            "author": self.author,
            "date": self.date.isoformat(),
        }


@dataclass
class PullRequest:
    """Represents a GitHub pull request."""

    number: int
    title: str
    created_at: datetime
    author: str
    age_days: int
    url: str

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "number": self.number,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "author": self.author,
            "age_days": self.age_days,
            "url": self.url,
        }


@dataclass
class CIRun:
    """Represents a CI/CD run."""

    name: str
    status: str
    conclusion: str | None
    created_at: datetime

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "status": self.status,
            "conclusion": self.conclusion,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Repository:
    """Represents a GitHub repository with collected metrics."""

    name: str
    owner: str
    full_name: str
    url: str
    last_commit: Commit | None
    open_prs: list[PullRequest]
    branches_without_prs: list[str]
    github_pages_enabled: bool
    github_pages_url: str | None
    ci_status: CIStatus
    ci_recent_runs: list[CIRun]
    ci_success_rate: float
    last_updated: datetime
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    primary_language: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "owner": self.owner,
            "full_name": self.full_name,
            "url": self.url,
            "last_commit": self.last_commit.to_dict() if self.last_commit else None,
            "open_prs": [pr.to_dict() for pr in self.open_prs],
            "pr_count": len(self.open_prs),
            "branches_without_prs": self.branches_without_prs,
            "branch_without_pr_count": len(self.branches_without_prs),
            "github_pages": {
                "enabled": self.github_pages_enabled,
                "url": self.github_pages_url,
            },
            "ci": {
                "status": self.ci_status.value,
                "recent_runs": [run.to_dict() for run in self.ci_recent_runs],
                "success_rate": self.ci_success_rate,
            },
            "last_updated": self.last_updated.isoformat(),
            "stats": {
                "stars": self.stars,
                "forks": self.forks,
                "open_issues": self.open_issues,
                "language": self.primary_language,
            },
        }


@dataclass
class MonitorReport:
    """Complete monitoring report for multiple repositories."""

    generated_at: datetime
    scan_period_days: int
    repositories: list[Repository]
    total_repositories: int = field(init=False)
    total_open_prs: int = field(init=False)
    total_branches_without_prs: int = field(init=False)

    def __post_init__(self):
        """Calculate aggregated metrics."""
        self.total_repositories = len(self.repositories)
        self.total_open_prs = sum(len(r.open_prs) for r in self.repositories)
        self.total_branches_without_prs = sum(
            len(r.branches_without_prs) for r in self.repositories
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for TOON/JSON output."""
        return {
            "report_metadata": {
                "generated_at": self.generated_at.isoformat(),
                "scan_period_days": self.scan_period_days,
                "total_repositories": self.total_repositories,
                "total_open_prs": self.total_open_prs,
                "total_branches_without_prs": self.total_branches_without_prs,
            },
            "repositories": [repo.to_dict() for repo in self.repositories],
        }


class SyncAction(Enum):
    """Action taken during sync."""

    CLONED = "cloned"
    PULLED = "pulled"
    SKIPPED_DIRTY = "skipped_dirty"
    SKIPPED_ERROR = "skipped_error"
    ALREADY_CURRENT = "already_current"


@dataclass
class SyncResult:
    """Result of syncing a single repository."""

    repo_name: str
    action: SyncAction
    message: str
    branch: str | None = None


@dataclass
class SyncReport:
    """Summary of sync operation."""

    cloned: list[str] = field(default_factory=list)
    pulled: list[str] = field(default_factory=list)
    already_current: list[str] = field(default_factory=list)
    skipped_dirty: list[str] = field(default_factory=list)
    skipped_error: list[str] = field(default_factory=list)

    def add_result(self, result: SyncResult) -> None:
        """Add a sync result to the appropriate list."""
        if result.action == SyncAction.CLONED:
            self.cloned.append(result.repo_name)
        elif result.action == SyncAction.PULLED:
            self.pulled.append(result.repo_name)
        elif result.action == SyncAction.ALREADY_CURRENT:
            self.already_current.append(result.repo_name)
        elif result.action == SyncAction.SKIPPED_DIRTY:
            self.skipped_dirty.append(result.repo_name)
        elif result.action == SyncAction.SKIPPED_ERROR:
            self.skipped_error.append(result.repo_name)
