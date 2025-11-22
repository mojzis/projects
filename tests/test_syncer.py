"""Tests for git syncer functionality."""

from pathlib import Path
from unittest.mock import patch

from gh_monitor.models import SyncAction, SyncReport, SyncResult
from gh_monitor.syncer import GitSyncer


class TestSyncModels:
    """Tests for sync-related models."""

    def test_sync_result_creation(self):
        """Test SyncResult dataclass."""
        result = SyncResult(
            repo_name="test-repo",
            action=SyncAction.CLONED,
            message="Cloned successfully",
            branch=None,
        )
        assert result.repo_name == "test-repo"
        assert result.action == SyncAction.CLONED
        assert result.message == "Cloned successfully"

    def test_sync_report_add_cloned(self):
        """Test adding cloned result to report."""
        report = SyncReport()
        result = SyncResult("repo1", SyncAction.CLONED, "Cloned")
        report.add_result(result)

        assert "repo1" in report.cloned
        assert len(report.pulled) == 0

    def test_sync_report_add_pulled(self):
        """Test adding pulled result to report."""
        report = SyncReport()
        result = SyncResult("repo1", SyncAction.PULLED, "Pulled", branch="main")
        report.add_result(result)

        assert "repo1" in report.pulled
        assert len(report.cloned) == 0

    def test_sync_report_add_already_current(self):
        """Test adding already current result to report."""
        report = SyncReport()
        result = SyncResult("repo1", SyncAction.ALREADY_CURRENT, "Up to date")
        report.add_result(result)

        assert "repo1" in report.already_current

    def test_sync_report_add_skipped_dirty(self):
        """Test adding skipped dirty result to report."""
        report = SyncReport()
        result = SyncResult("repo1", SyncAction.SKIPPED_DIRTY, "Has changes")
        report.add_result(result)

        assert "repo1" in report.skipped_dirty

    def test_sync_report_add_skipped_error(self):
        """Test adding skipped error result to report."""
        report = SyncReport()
        result = SyncResult("repo1", SyncAction.SKIPPED_ERROR, "Failed")
        report.add_result(result)

        assert "repo1" in report.skipped_error

    def test_sync_report_multiple_results(self):
        """Test adding multiple results to report."""
        report = SyncReport()
        report.add_result(SyncResult("repo1", SyncAction.CLONED, "Cloned"))
        report.add_result(SyncResult("repo2", SyncAction.PULLED, "Pulled"))
        report.add_result(SyncResult("repo3", SyncAction.ALREADY_CURRENT, "Current"))
        report.add_result(SyncResult("repo4", SyncAction.SKIPPED_DIRTY, "Dirty"))

        assert len(report.cloned) == 1
        assert len(report.pulled) == 1
        assert len(report.already_current) == 1
        assert len(report.skipped_dirty) == 1


class TestGitSyncer:
    """Tests for GitSyncer class."""

    def test_init(self, tmp_path):
        """Test GitSyncer initialization."""
        syncer = GitSyncer("test-owner", tmp_path, verbose=False)
        assert syncer.owner == "test-owner"
        assert syncer.git_dir == tmp_path
        assert syncer.verbose is False

    def test_init_expands_home(self):
        """Test that ~ is expanded in git_dir."""
        syncer = GitSyncer("test-owner", Path("~/git"), verbose=False)
        assert "~" not in str(syncer.git_dir)

    @patch.object(GitSyncer, "_run_git")
    def test_is_git_clean_true(self, mock_run_git, tmp_path):
        """Test _is_git_clean returns True for clean repo."""
        mock_run_git.return_value = (True, "")
        syncer = GitSyncer("test-owner", tmp_path)

        assert syncer._is_git_clean(tmp_path) is True
        mock_run_git.assert_called_once_with(["status", "--porcelain"], cwd=tmp_path)

    @patch.object(GitSyncer, "_run_git")
    def test_is_git_clean_false(self, mock_run_git, tmp_path):
        """Test _is_git_clean returns False for dirty repo."""
        mock_run_git.return_value = (True, " M file.txt")
        syncer = GitSyncer("test-owner", tmp_path)

        assert syncer._is_git_clean(tmp_path) is False

    @patch.object(GitSyncer, "_run_git")
    def test_get_current_branch(self, mock_run_git, tmp_path):
        """Test _get_current_branch returns branch name."""
        mock_run_git.return_value = (True, "main")
        syncer = GitSyncer("test-owner", tmp_path)

        assert syncer._get_current_branch(tmp_path) == "main"

    @patch.object(GitSyncer, "_run_git")
    def test_clone_repo_success(self, mock_run_git, tmp_path):
        """Test successful clone."""
        mock_run_git.return_value = (True, "Cloning...")
        syncer = GitSyncer("test-owner", tmp_path)

        result = syncer._clone_repo("test-repo", "git@github.com:owner/test-repo.git")

        assert result.action == SyncAction.CLONED
        assert result.repo_name == "test-repo"

    @patch.object(GitSyncer, "_run_git")
    def test_clone_repo_failure(self, mock_run_git, tmp_path):
        """Test failed clone."""
        mock_run_git.return_value = (False, "Permission denied")
        syncer = GitSyncer("test-owner", tmp_path)

        result = syncer._clone_repo("test-repo", "git@github.com:owner/test-repo.git")

        assert result.action == SyncAction.SKIPPED_ERROR
        assert "Permission denied" in result.message

    @patch.object(GitSyncer, "_is_git_clean")
    @patch.object(GitSyncer, "_get_current_branch")
    def test_pull_repo_dirty(self, mock_branch, mock_clean, tmp_path):
        """Test pull skipped for dirty repo."""
        mock_clean.return_value = False
        mock_branch.return_value = "main"
        syncer = GitSyncer("test-owner", tmp_path)

        result = syncer._pull_repo("test-repo", tmp_path)

        assert result.action == SyncAction.SKIPPED_DIRTY
        assert result.branch == "main"

    @patch.object(GitSyncer, "_run_git")
    @patch.object(GitSyncer, "_is_git_clean")
    @patch.object(GitSyncer, "_get_current_branch")
    @patch.object(GitSyncer, "_needs_pull")
    def test_pull_repo_already_current(
        self, mock_needs_pull, mock_branch, mock_clean, mock_run_git, tmp_path
    ):
        """Test pull skipped when already current."""
        mock_clean.return_value = True
        mock_branch.return_value = "main"
        mock_needs_pull.return_value = False
        syncer = GitSyncer("test-owner", tmp_path)

        result = syncer._pull_repo("test-repo", tmp_path)

        assert result.action == SyncAction.ALREADY_CURRENT

    @patch.object(GitSyncer, "_run_git")
    @patch.object(GitSyncer, "_is_git_clean")
    @patch.object(GitSyncer, "_get_current_branch")
    @patch.object(GitSyncer, "_needs_pull")
    def test_pull_repo_success(
        self, mock_needs_pull, mock_branch, mock_clean, mock_run_git, tmp_path
    ):
        """Test successful pull."""
        mock_clean.return_value = True
        mock_branch.return_value = "main"
        mock_needs_pull.return_value = True
        mock_run_git.return_value = (True, "Already up to date.")
        syncer = GitSyncer("test-owner", tmp_path)

        result = syncer._pull_repo("test-repo", tmp_path)

        assert result.action == SyncAction.PULLED
