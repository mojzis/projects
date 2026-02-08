"""Tests for GitHub CLI collector."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from gh_monitor.collector import GitHubCLIError, GitHubCollector


class TestGitHubCollector:
    """Tests for GitHubCollector class."""

    @pytest.fixture
    def collector(self):
        """Create a collector instance."""
        return GitHubCollector(verbose=False)

    @pytest.fixture
    def verbose_collector(self):
        """Create a verbose collector instance."""
        return GitHubCollector(verbose=True)


class TestRunGh:
    """Tests for _run_gh method."""

    @pytest.fixture
    def collector(self):
        return GitHubCollector()

    def test_run_gh_success(self, collector):
        """Test successful gh command execution."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"key": "value"}'

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = collector._run_gh(["repo", "list"])

            mock_run.assert_called_once_with(
                ["gh", "repo", "list"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            assert result == {"key": "value"}

    def test_run_gh_returns_list(self, collector):
        """Test gh command returning a list."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '[{"name": "repo1"}, {"name": "repo2"}]'

        with patch("subprocess.run", return_value=mock_result):
            result = collector._run_gh(["repo", "list"])
            assert isinstance(result, list)
            assert len(result) == 2

    def test_run_gh_empty_output(self, collector):
        """Test gh command with empty output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            result = collector._run_gh(["repo", "list"])
            assert result == {}

    def test_run_gh_whitespace_output(self, collector):
        """Test gh command with whitespace-only output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "   \n   "

        with patch("subprocess.run", return_value=mock_result):
            result = collector._run_gh(["repo", "list"])
            assert result == {}

    def test_run_gh_failure(self, collector):
        """Test gh command failure raises GitHubCLIError."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "gh: not authenticated"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(GitHubCLIError) as exc_info:
                collector._run_gh(["repo", "list"])

            assert "gh command failed" in str(exc_info.value)
            assert "not authenticated" in str(exc_info.value)


class TestGetRepositories:
    """Tests for get_repositories method."""

    @pytest.fixture
    def collector(self):
        return GitHubCollector()

    def test_get_repositories_filters_by_date(self, collector):
        """Test that repositories are filtered by pushed date."""
        now = datetime.now(UTC)
        recent = (now - timedelta(days=5)).isoformat()
        old = (now - timedelta(days=60)).isoformat()

        repos = [
            {"name": "recent-repo", "pushedAt": recent, "url": "https://github.com/o/r1"},
            {"name": "old-repo", "pushedAt": old, "url": "https://github.com/o/r2"},
        ]

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(repos)

        with patch("subprocess.run", return_value=mock_result):
            result = collector.get_repositories("test-owner", since_days=30)

            assert len(result) == 1
            assert result[0]["name"] == "recent-repo"

    def test_get_repositories_empty_list(self, collector):
        """Test getting empty repository list."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "[]"

        with patch("subprocess.run", return_value=mock_result):
            result = collector.get_repositories("empty-owner")
            assert result == []


class TestGetLastCommit:
    """Tests for get_last_commit method."""

    @pytest.fixture
    def collector(self):
        return GitHubCollector()

    def test_get_last_commit_main_branch(self, collector):
        """Test getting last commit from main branch."""
        commit_data = {"sha": "abc123", "commit": {"message": "test"}}

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(commit_data)

        with patch("subprocess.run", return_value=mock_result):
            result = collector.get_last_commit("owner", "repo")
            assert result["sha"] == "abc123"

    def test_get_last_commit_fallback_to_master(self, collector):
        """Test fallback to master branch when main fails."""
        commit_data = {"sha": "def456", "commit": {"message": "test"}}

        def mock_run(*args, **kwargs):
            mock_result = MagicMock()
            if "main" in args[0]:
                mock_result.returncode = 1
                mock_result.stderr = "not found"
            else:
                mock_result.returncode = 0
                mock_result.stdout = json.dumps(commit_data)
            return mock_result

        with patch("subprocess.run", side_effect=mock_run):
            result = collector.get_last_commit("owner", "repo")
            assert result["sha"] == "def456"

    def test_get_last_commit_both_branches_fail(self, collector):
        """Test returning None when both branches fail."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "not found"

        with patch("subprocess.run", return_value=mock_result):
            result = collector.get_last_commit("owner", "repo")
            assert result is None


class TestGetOpenPRs:
    """Tests for get_open_prs method."""

    @pytest.fixture
    def collector(self):
        return GitHubCollector()

    def test_get_open_prs_success(self, collector):
        """Test getting open pull requests."""
        prs = [
            {"number": 1, "title": "PR 1", "createdAt": "2025-01-10T10:00:00Z"},
            {"number": 2, "title": "PR 2", "createdAt": "2025-01-11T10:00:00Z"},
        ]

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(prs)

        with patch("subprocess.run", return_value=mock_result):
            result = collector.get_open_prs("owner", "repo")
            assert len(result) == 2

    def test_get_open_prs_empty(self, collector):
        """Test getting empty PR list."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "[]"

        with patch("subprocess.run", return_value=mock_result):
            result = collector.get_open_prs("owner", "repo")
            assert result == []

    def test_get_open_prs_error(self, collector):
        """Test PR fetch error returns empty list."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error"

        with patch("subprocess.run", return_value=mock_result):
            result = collector.get_open_prs("owner", "repo")
            assert result == []


class TestGetBranches:
    """Tests for get_branches method."""

    @pytest.fixture
    def collector(self):
        return GitHubCollector()

    def test_get_branches_success(self, collector):
        """Test getting branch names."""
        branches = [{"name": "main"}, {"name": "feature-1"}, {"name": "feature-2"}]

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(branches)

        with patch("subprocess.run", return_value=mock_result):
            result = collector.get_branches("owner", "repo")
            assert result == ["main", "feature-1", "feature-2"]

    def test_get_branches_error(self, collector):
        """Test branch fetch error returns empty list."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error"

        with patch("subprocess.run", return_value=mock_result):
            result = collector.get_branches("owner", "repo")
            assert result == []


class TestGetPRBranches:
    """Tests for get_pr_branches method."""

    @pytest.fixture
    def collector(self):
        return GitHubCollector()

    def test_get_pr_branches_success(self, collector):
        """Test getting PR branch names."""
        prs = [{"headRefName": "feature-1"}, {"headRefName": "feature-2"}]

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(prs)

        with patch("subprocess.run", return_value=mock_result):
            result = collector.get_pr_branches("owner", "repo")
            assert result == {"feature-1", "feature-2"}

    def test_get_pr_branches_error(self, collector):
        """Test PR branches fetch error returns empty set."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error"

        with patch("subprocess.run", return_value=mock_result):
            result = collector.get_pr_branches("owner", "repo")
            assert result == set()


class TestGetGitHubPages:
    """Tests for get_github_pages method."""

    @pytest.fixture
    def collector(self):
        return GitHubCollector()

    def test_get_github_pages_enabled(self, collector):
        """Test getting GitHub Pages when enabled."""
        pages = {"html_url": "https://owner.github.io/repo"}

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(pages)

        with patch("subprocess.run", return_value=mock_result):
            result = collector.get_github_pages("owner", "repo")
            assert result["html_url"] == "https://owner.github.io/repo"

    def test_get_github_pages_disabled(self, collector):
        """Test GitHub Pages when not enabled."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Not Found"

        with patch("subprocess.run", return_value=mock_result):
            result = collector.get_github_pages("owner", "repo")
            assert result is None


class TestGetCIRuns:
    """Tests for get_ci_runs method."""

    @pytest.fixture
    def collector(self):
        return GitHubCollector()

    def test_get_ci_runs_success(self, collector):
        """Test getting CI runs."""
        runs = [
            {"name": "Build", "status": "completed", "conclusion": "success"},
            {"name": "Test", "status": "completed", "conclusion": "failure"},
        ]

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(runs)

        with patch("subprocess.run", return_value=mock_result):
            result = collector.get_ci_runs("owner", "repo")
            assert len(result) == 2

    def test_get_ci_runs_error(self, collector):
        """Test CI runs fetch error returns empty list."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error"

        with patch("subprocess.run", return_value=mock_result):
            result = collector.get_ci_runs("owner", "repo")
            assert result == []


class TestGetRepoDetails:
    """Tests for get_repo_details method."""

    @pytest.fixture
    def collector(self):
        return GitHubCollector()

    def test_get_repo_details_success(self, collector):
        """Test getting repository details."""
        details = {
            "stargazerCount": 100,
            "forkCount": 20,
            "openIssues": {"totalCount": 5},
            "primaryLanguage": {"name": "Python"},
        }

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(details)

        with patch("subprocess.run", return_value=mock_result):
            result = collector.get_repo_details("owner", "repo")
            assert result["stargazerCount"] == 100

    def test_get_repo_details_error(self, collector):
        """Test repo details fetch error returns empty dict."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error"

        with patch("subprocess.run", return_value=mock_result):
            result = collector.get_repo_details("owner", "repo")
            assert result == {}
