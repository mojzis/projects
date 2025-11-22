"""Tests for ProjectMonitor orchestration."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from gh_monitor.models import CIStatus
from gh_monitor.monitor import ProjectMonitor


class TestProjectMonitor:
    """Tests for ProjectMonitor class."""

    @pytest.fixture
    def monitor(self):
        """Create a monitor instance with mocked collector."""
        return ProjectMonitor(owner="test-owner", days=30, verbose=False)

    @pytest.fixture
    def mock_collector(self):
        """Create a mocked collector."""
        collector = MagicMock()
        return collector


class TestCollectAllData:
    """Tests for collect_all_data method."""

    def test_collect_all_data_empty(self):
        """Test collecting data when no repositories exist."""
        monitor = ProjectMonitor(owner="empty-owner", days=30)

        with patch.object(monitor.collector, "get_repositories", return_value=[]):
            result = monitor.collect_all_data()
            assert result == []

    def test_collect_all_data_with_repos(self):
        """Test collecting data for repositories."""
        monitor = ProjectMonitor(owner="test-owner", days=30)

        repo_info = {
            "name": "test-repo",
            "url": "https://github.com/test-owner/test-repo",
        }

        with patch.object(
            monitor.collector, "get_repositories", return_value=[repo_info]
        ), patch.object(
            monitor.collector, "get_last_commit", return_value=None
        ), patch.object(
            monitor.collector, "get_open_prs", return_value=[]
        ), patch.object(
            monitor.collector, "get_branches", return_value=["main"]
        ), patch.object(
            monitor.collector, "get_pr_branches", return_value=set()
        ), patch.object(
            monitor.collector, "get_github_pages", return_value=None
        ), patch.object(
            monitor.collector, "get_ci_runs", return_value=[]
        ), patch.object(
            monitor.collector, "get_repo_details", return_value={}
        ):
            result = monitor.collect_all_data()

            assert len(result) == 1
            assert result[0].name == "test-repo"
            assert result[0].owner == "test-owner"

    def test_collect_all_data_with_progress_callback(self):
        """Test progress callback is called correctly."""
        monitor = ProjectMonitor(owner="test-owner", days=30)

        repos = [
            {"name": "repo1", "url": "https://github.com/test-owner/repo1"},
            {"name": "repo2", "url": "https://github.com/test-owner/repo2"},
        ]

        progress_values = []

        def track_progress(p):
            progress_values.append(p)

        with patch.object(
            monitor.collector, "get_repositories", return_value=repos
        ), patch.object(
            monitor.collector, "get_last_commit", return_value=None
        ), patch.object(
            monitor.collector, "get_open_prs", return_value=[]
        ), patch.object(
            monitor.collector, "get_branches", return_value=[]
        ), patch.object(
            monitor.collector, "get_pr_branches", return_value=set()
        ), patch.object(
            monitor.collector, "get_github_pages", return_value=None
        ), patch.object(
            monitor.collector, "get_ci_runs", return_value=[]
        ), patch.object(
            monitor.collector, "get_repo_details", return_value={}
        ):
            monitor.collect_all_data(progress_callback=track_progress)

            assert len(progress_values) == 2
            assert progress_values[-1] == 100


class TestGetLastCommit:
    """Tests for _get_last_commit method."""

    def test_get_last_commit_success(self):
        """Test parsing last commit data."""
        monitor = ProjectMonitor(owner="test-owner", days=30)

        commit_data = {
            "sha": "abc123",
            "commit": {
                "message": "Fix bug\n\nDetailed description",
                "author": {"name": "John Doe", "date": "2025-01-15T12:00:00Z"},
            },
        }

        with patch.object(
            monitor.collector, "get_last_commit", return_value=commit_data
        ):
            result = monitor._get_last_commit("test-repo")

            assert result is not None
            assert result.sha == "abc123"
            assert result.message == "Fix bug"  # First line only
            assert result.author == "John Doe"

    def test_get_last_commit_none(self):
        """Test when no commit is available."""
        monitor = ProjectMonitor(owner="test-owner", days=30)

        with patch.object(monitor.collector, "get_last_commit", return_value=None):
            result = monitor._get_last_commit("test-repo")
            assert result is None


class TestGetOpenPRs:
    """Tests for _get_open_prs method."""

    def test_get_open_prs_success(self):
        """Test parsing open PRs."""
        monitor = ProjectMonitor(owner="test-owner", days=30)

        prs_data = [
            {
                "number": 1,
                "title": "Add feature",
                "createdAt": "2025-01-10T10:00:00Z",
                "author": {"login": "developer"},
                "url": "https://github.com/test-owner/repo/pull/1",
            }
        ]

        with patch.object(monitor.collector, "get_open_prs", return_value=prs_data):
            result = monitor._get_open_prs("test-repo")

            assert len(result) == 1
            assert result[0].number == 1
            assert result[0].title == "Add feature"
            assert result[0].author == "developer"

    def test_get_open_prs_missing_author(self):
        """Test handling PR with missing author."""
        monitor = ProjectMonitor(owner="test-owner", days=30)

        prs_data = [
            {
                "number": 1,
                "title": "Add feature",
                "createdAt": "2025-01-10T10:00:00Z",
                "author": None,
                "url": "https://github.com/test-owner/repo/pull/1",
            }
        ]

        with patch.object(monitor.collector, "get_open_prs", return_value=prs_data):
            result = monitor._get_open_prs("test-repo")

            assert len(result) == 1
            assert result[0].author == "Unknown"


class TestGetBranchesWithoutPRs:
    """Tests for _get_branches_without_prs method."""

    def test_branches_without_prs(self):
        """Test finding branches without PRs."""
        monitor = ProjectMonitor(owner="test-owner", days=30)

        with patch.object(
            monitor.collector,
            "get_branches",
            return_value=["main", "feature-1", "feature-2", "bugfix-1"],
        ), patch.object(
            monitor.collector, "get_pr_branches", return_value={"feature-1"}
        ):
            result = monitor._get_branches_without_prs("test-repo")

            assert "feature-2" in result
            assert "bugfix-1" in result
            assert "main" not in result
            assert "feature-1" not in result

    def test_branches_excludes_main_and_master(self):
        """Test that main and master are always excluded."""
        monitor = ProjectMonitor(owner="test-owner", days=30)

        with patch.object(
            monitor.collector,
            "get_branches",
            return_value=["main", "master", "feature-1"],
        ), patch.object(monitor.collector, "get_pr_branches", return_value=set()):
            result = monitor._get_branches_without_prs("test-repo")

            assert "main" not in result
            assert "master" not in result
            assert "feature-1" in result


class TestGetGitHubPages:
    """Tests for _get_github_pages method."""

    def test_github_pages_enabled(self):
        """Test when GitHub Pages is enabled."""
        monitor = ProjectMonitor(owner="test-owner", days=30)

        pages_data = {"html_url": "https://test-owner.github.io/repo"}

        with patch.object(
            monitor.collector, "get_github_pages", return_value=pages_data
        ):
            enabled, url = monitor._get_github_pages("test-repo")

            assert enabled is True
            assert url == "https://test-owner.github.io/repo"

    def test_github_pages_disabled(self):
        """Test when GitHub Pages is disabled."""
        monitor = ProjectMonitor(owner="test-owner", days=30)

        with patch.object(monitor.collector, "get_github_pages", return_value=None):
            enabled, url = monitor._get_github_pages("test-repo")

            assert enabled is False
            assert url is None


class TestGetCIInfo:
    """Tests for _get_ci_info method."""

    def test_ci_info_no_ci(self):
        """Test when no CI runs exist."""
        monitor = ProjectMonitor(owner="test-owner", days=30)

        with patch.object(monitor.collector, "get_ci_runs", return_value=[]):
            status, runs, rate = monitor._get_ci_info("test-repo")

            assert status == CIStatus.NO_CI
            assert runs == []
            assert rate == 0.0

    def test_ci_info_success(self):
        """Test CI with successful runs."""
        monitor = ProjectMonitor(owner="test-owner", days=30)

        runs_data = [
            {
                "name": "Build",
                "status": "completed",
                "conclusion": "success",
                "createdAt": "2025-01-15T12:00:00Z",
            },
            {
                "name": "Test",
                "status": "completed",
                "conclusion": "success",
                "createdAt": "2025-01-14T12:00:00Z",
            },
        ]

        with patch.object(monitor.collector, "get_ci_runs", return_value=runs_data):
            status, runs, rate = monitor._get_ci_info("test-repo")

            assert status == CIStatus.SUCCESS
            assert len(runs) == 2
            assert rate == 1.0

    def test_ci_info_failure(self):
        """Test CI with failed latest run."""
        monitor = ProjectMonitor(owner="test-owner", days=30)

        runs_data = [
            {
                "name": "Build",
                "status": "completed",
                "conclusion": "failure",
                "createdAt": "2025-01-15T12:00:00Z",
            },
            {
                "name": "Build",
                "status": "completed",
                "conclusion": "success",
                "createdAt": "2025-01-14T12:00:00Z",
            },
        ]

        with patch.object(monitor.collector, "get_ci_runs", return_value=runs_data):
            status, runs, rate = monitor._get_ci_info("test-repo")

            assert status == CIStatus.FAILURE
            assert len(runs) == 2
            assert rate == 0.5

    def test_ci_info_pending(self):
        """Test CI with pending runs only."""
        monitor = ProjectMonitor(owner="test-owner", days=30)

        runs_data = [
            {
                "name": "Build",
                "status": "in_progress",
                "conclusion": None,
                "createdAt": "2025-01-15T12:00:00Z",
            },
        ]

        with patch.object(monitor.collector, "get_ci_runs", return_value=runs_data):
            status, runs, rate = monitor._get_ci_info("test-repo")

            assert status == CIStatus.PENDING
            assert len(runs) == 1
            assert rate == 0.0


class TestCollectRepoData:
    """Tests for _collect_repo_data method."""

    def test_collect_repo_data_full(self):
        """Test collecting full repository data."""
        monitor = ProjectMonitor(owner="test-owner", days=30)

        repo_info = {"name": "test-repo", "url": "https://github.com/test-owner/test-repo"}

        commit_data = {
            "sha": "abc123",
            "commit": {
                "message": "Latest commit",
                "author": {"name": "Author", "date": "2025-01-15T12:00:00Z"},
            },
        }

        repo_details = {
            "stargazerCount": 50,
            "forkCount": 10,
            "openIssues": {"totalCount": 3},
            "primaryLanguage": {"name": "Python"},
        }

        with patch.object(
            monitor.collector, "get_last_commit", return_value=commit_data
        ), patch.object(
            monitor.collector, "get_open_prs", return_value=[]
        ), patch.object(
            monitor.collector, "get_branches", return_value=["main"]
        ), patch.object(
            monitor.collector, "get_pr_branches", return_value=set()
        ), patch.object(
            monitor.collector, "get_github_pages", return_value=None
        ), patch.object(
            monitor.collector, "get_ci_runs", return_value=[]
        ), patch.object(
            monitor.collector, "get_repo_details", return_value=repo_details
        ):
            result = monitor._collect_repo_data("test-repo", repo_info)

            assert result.name == "test-repo"
            assert result.owner == "test-owner"
            assert result.stars == 50
            assert result.primary_language == "Python"
            assert result.last_commit is not None
            assert result.last_commit.sha == "abc123"
