"""Tests for data models."""

from datetime import datetime, timezone

import pytest

from gh_monitor.models import (
    CIRun,
    CIStatus,
    Commit,
    MonitorReport,
    PullRequest,
    Repository,
)


class TestCIStatus:
    """Tests for CIStatus enum."""

    def test_ci_status_values(self):
        """Test all CI status values are accessible."""
        assert CIStatus.SUCCESS.value == "success"
        assert CIStatus.FAILURE.value == "failure"
        assert CIStatus.PENDING.value == "pending"
        assert CIStatus.NO_CI.value == "no_ci"
        assert CIStatus.UNKNOWN.value == "unknown"


class TestCommit:
    """Tests for Commit dataclass."""

    def test_commit_creation(self):
        """Test creating a commit."""
        commit = Commit(
            sha="abc123def456",
            message="Add feature X",
            author="John Doe",
            date=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert commit.sha == "abc123def456"
        assert commit.message == "Add feature X"
        assert commit.author == "John Doe"

    def test_commit_to_dict(self):
        """Test commit serialization."""
        commit = Commit(
            sha="abc123",
            message="Test commit",
            author="Test Author",
            date=datetime(2025, 1, 1, 12, 0, 0),
        )
        data = commit.to_dict()
        assert data["sha"] == "abc123"
        assert data["message"] == "Test commit"
        assert data["author"] == "Test Author"
        assert data["date"] == "2025-01-01T12:00:00"

    def test_commit_to_dict_with_timezone(self):
        """Test commit serialization with timezone."""
        commit = Commit(
            sha="abc123",
            message="Test commit",
            author="Test Author",
            date=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        data = commit.to_dict()
        assert "2025-01-01T12:00:00" in data["date"]


class TestPullRequest:
    """Tests for PullRequest dataclass."""

    def test_pull_request_creation(self):
        """Test creating a pull request."""
        pr = PullRequest(
            number=42,
            title="Fix bug in parser",
            created_at=datetime(2025, 1, 10, 10, 0, 0, tzinfo=timezone.utc),
            author="janedoe",
            age_days=5,
            url="https://github.com/owner/repo/pull/42",
        )
        assert pr.number == 42
        assert pr.title == "Fix bug in parser"
        assert pr.author == "janedoe"
        assert pr.age_days == 5

    def test_pull_request_to_dict(self):
        """Test pull request serialization."""
        pr = PullRequest(
            number=42,
            title="Fix bug",
            created_at=datetime(2025, 1, 10, 10, 0, 0),
            author="janedoe",
            age_days=5,
            url="https://github.com/owner/repo/pull/42",
        )
        data = pr.to_dict()
        assert data["number"] == 42
        assert data["title"] == "Fix bug"
        assert data["author"] == "janedoe"
        assert data["age_days"] == 5
        assert data["url"] == "https://github.com/owner/repo/pull/42"
        assert "created_at" in data


class TestCIRun:
    """Tests for CIRun dataclass."""

    def test_ci_run_creation(self):
        """Test creating a CI run."""
        run = CIRun(
            name="Build",
            status="completed",
            conclusion="success",
            created_at=datetime(2025, 1, 15, 8, 0, 0, tzinfo=timezone.utc),
        )
        assert run.name == "Build"
        assert run.status == "completed"
        assert run.conclusion == "success"

    def test_ci_run_with_null_conclusion(self):
        """Test CI run with pending status (no conclusion)."""
        run = CIRun(
            name="Test",
            status="in_progress",
            conclusion=None,
            created_at=datetime(2025, 1, 15, 8, 0, 0, tzinfo=timezone.utc),
        )
        assert run.conclusion is None

    def test_ci_run_to_dict(self):
        """Test CI run serialization."""
        run = CIRun(
            name="Build",
            status="completed",
            conclusion="success",
            created_at=datetime(2025, 1, 15, 8, 0, 0),
        )
        data = run.to_dict()
        assert data["name"] == "Build"
        assert data["status"] == "completed"
        assert data["conclusion"] == "success"
        assert "created_at" in data


class TestRepository:
    """Tests for Repository dataclass."""

    @pytest.fixture
    def sample_commit(self):
        """Create a sample commit for testing."""
        return Commit(
            sha="abc123",
            message="Latest commit",
            author="Author",
            date=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        )

    @pytest.fixture
    def sample_pr(self):
        """Create a sample PR for testing."""
        return PullRequest(
            number=1,
            title="Test PR",
            created_at=datetime(2025, 1, 10, 10, 0, 0, tzinfo=timezone.utc),
            author="author",
            age_days=5,
            url="https://github.com/owner/repo/pull/1",
        )

    @pytest.fixture
    def sample_ci_run(self):
        """Create a sample CI run for testing."""
        return CIRun(
            name="CI",
            status="completed",
            conclusion="success",
            created_at=datetime(2025, 1, 15, 8, 0, 0, tzinfo=timezone.utc),
        )

    def test_repository_creation(self, sample_commit, sample_pr, sample_ci_run):
        """Test creating a repository with all data."""
        repo = Repository(
            name="test-repo",
            owner="test-owner",
            full_name="test-owner/test-repo",
            url="https://github.com/test-owner/test-repo",
            last_commit=sample_commit,
            open_prs=[sample_pr],
            branches_without_prs=["feature-1"],
            github_pages_enabled=True,
            github_pages_url="https://test-owner.github.io/test-repo",
            ci_status=CIStatus.SUCCESS,
            ci_recent_runs=[sample_ci_run],
            ci_success_rate=0.95,
            last_updated=datetime.now(timezone.utc),
            stars=100,
            forks=20,
            open_issues=5,
            primary_language="Python",
        )
        assert repo.name == "test-repo"
        assert repo.owner == "test-owner"
        assert repo.github_pages_enabled is True
        assert repo.ci_status == CIStatus.SUCCESS
        assert repo.stars == 100

    def test_repository_without_optional_fields(self):
        """Test repository with minimal data."""
        repo = Repository(
            name="minimal-repo",
            owner="owner",
            full_name="owner/minimal-repo",
            url="https://github.com/owner/minimal-repo",
            last_commit=None,
            open_prs=[],
            branches_without_prs=[],
            github_pages_enabled=False,
            github_pages_url=None,
            ci_status=CIStatus.NO_CI,
            ci_recent_runs=[],
            ci_success_rate=0.0,
            last_updated=datetime.now(timezone.utc),
        )
        assert repo.last_commit is None
        assert repo.stars == 0
        assert repo.primary_language is None

    def test_repository_to_dict(self, sample_commit, sample_pr, sample_ci_run):
        """Test repository serialization."""
        repo = Repository(
            name="test-repo",
            owner="test-owner",
            full_name="test-owner/test-repo",
            url="https://github.com/test-owner/test-repo",
            last_commit=sample_commit,
            open_prs=[sample_pr],
            branches_without_prs=["feature-1", "feature-2"],
            github_pages_enabled=True,
            github_pages_url="https://test-owner.github.io/test-repo",
            ci_status=CIStatus.SUCCESS,
            ci_recent_runs=[sample_ci_run],
            ci_success_rate=0.95,
            last_updated=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            stars=100,
            forks=20,
            open_issues=5,
            primary_language="Python",
        )
        data = repo.to_dict()

        assert data["name"] == "test-repo"
        assert data["pr_count"] == 1
        assert data["branch_without_pr_count"] == 2
        assert data["github_pages"]["enabled"] is True
        assert data["ci"]["status"] == "success"
        assert data["ci"]["success_rate"] == 0.95
        assert data["stats"]["stars"] == 100
        assert data["stats"]["language"] == "Python"

    def test_repository_to_dict_without_commit(self):
        """Test repository serialization without last commit."""
        repo = Repository(
            name="test-repo",
            owner="test-owner",
            full_name="test-owner/test-repo",
            url="https://github.com/test-owner/test-repo",
            last_commit=None,
            open_prs=[],
            branches_without_prs=[],
            github_pages_enabled=False,
            github_pages_url=None,
            ci_status=CIStatus.NO_CI,
            ci_recent_runs=[],
            ci_success_rate=0.0,
            last_updated=datetime.now(timezone.utc),
        )
        data = repo.to_dict()
        assert data["last_commit"] is None


class TestMonitorReport:
    """Tests for MonitorReport dataclass."""

    @pytest.fixture
    def sample_repositories(self):
        """Create sample repositories for testing."""
        return [
            Repository(
                name="repo1",
                owner="owner",
                full_name="owner/repo1",
                url="https://github.com/owner/repo1",
                last_commit=None,
                open_prs=[
                    PullRequest(
                        number=1,
                        title="PR 1",
                        created_at=datetime.now(timezone.utc),
                        author="author",
                        age_days=1,
                        url="https://github.com/owner/repo1/pull/1",
                    ),
                    PullRequest(
                        number=2,
                        title="PR 2",
                        created_at=datetime.now(timezone.utc),
                        author="author",
                        age_days=2,
                        url="https://github.com/owner/repo1/pull/2",
                    ),
                ],
                branches_without_prs=["feature-1", "feature-2"],
                github_pages_enabled=False,
                github_pages_url=None,
                ci_status=CIStatus.SUCCESS,
                ci_recent_runs=[],
                ci_success_rate=1.0,
                last_updated=datetime.now(timezone.utc),
            ),
            Repository(
                name="repo2",
                owner="owner",
                full_name="owner/repo2",
                url="https://github.com/owner/repo2",
                last_commit=None,
                open_prs=[
                    PullRequest(
                        number=3,
                        title="PR 3",
                        created_at=datetime.now(timezone.utc),
                        author="author",
                        age_days=3,
                        url="https://github.com/owner/repo2/pull/3",
                    ),
                ],
                branches_without_prs=["feature-3"],
                github_pages_enabled=True,
                github_pages_url="https://owner.github.io/repo2",
                ci_status=CIStatus.FAILURE,
                ci_recent_runs=[],
                ci_success_rate=0.5,
                last_updated=datetime.now(timezone.utc),
            ),
        ]

    def test_monitor_report_aggregation(self, sample_repositories):
        """Test report aggregation of multiple repositories."""
        report = MonitorReport(
            generated_at=datetime.now(timezone.utc),
            scan_period_days=30,
            repositories=sample_repositories,
        )

        assert report.total_repositories == 2
        assert report.total_open_prs == 3
        assert report.total_branches_without_prs == 3

    def test_monitor_report_empty(self):
        """Test report with no repositories."""
        report = MonitorReport(
            generated_at=datetime.now(timezone.utc),
            scan_period_days=30,
            repositories=[],
        )

        assert report.total_repositories == 0
        assert report.total_open_prs == 0
        assert report.total_branches_without_prs == 0

    def test_monitor_report_to_dict(self, sample_repositories):
        """Test report serialization."""
        report = MonitorReport(
            generated_at=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            scan_period_days=30,
            repositories=sample_repositories,
        )
        data = report.to_dict()

        assert "report_metadata" in data
        assert data["report_metadata"]["scan_period_days"] == 30
        assert data["report_metadata"]["total_repositories"] == 2
        assert data["report_metadata"]["total_open_prs"] == 3
        assert data["report_metadata"]["total_branches_without_prs"] == 3
        assert "repositories" in data
        assert len(data["repositories"]) == 2
