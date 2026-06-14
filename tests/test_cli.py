"""Tests for CLI interface."""

import os
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gh_monitor.cli import _publish_to_gh_pages, app
from gh_monitor.models import CIStatus, Repository

runner = CliRunner()


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


class TestVersionCommand:
    """Tests for version command."""

    def test_version_command(self):
        """Test version command output."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.stdout


class TestMonitorCommand:
    """Tests for monitor command."""

    @pytest.fixture
    def mock_repository(self):
        """Create a mock repository."""
        return Repository(
            name="test-repo",
            owner="test-owner",
            full_name="test-owner/test-repo",
            url="https://github.com/test-owner/test-repo",
            last_commit=None,
            open_prs=[],
            branches_without_prs=[],
            github_pages_enabled=False,
            github_pages_url=None,
            ci_status=CIStatus.SUCCESS,
            ci_recent_runs=[],
            ci_success_rate=1.0,
            last_updated=datetime.now(UTC),
        )

    def test_monitor_no_repositories(self):
        """Test monitor when no repositories are found."""
        with patch("gh_monitor.cli.ProjectMonitor") as MockMonitor:
            mock_instance = MagicMock()
            mock_instance.collect_all_data.return_value = []
            MockMonitor.return_value = mock_instance

            with tempfile.TemporaryDirectory() as tmpdir:
                result = runner.invoke(
                    app, ["monitor", "empty-owner", "--output", tmpdir, "--format", "markdown"]
                )

                assert result.exit_code == 0
                assert "No repositories found" in result.stdout

    def test_monitor_with_repositories(self, mock_repository):
        """Test monitor with repositories found."""
        with patch("gh_monitor.cli.ProjectMonitor") as MockMonitor:
            mock_instance = MagicMock()
            mock_instance.collect_all_data.return_value = [mock_repository]
            MockMonitor.return_value = mock_instance

            with tempfile.TemporaryDirectory() as tmpdir:
                result = runner.invoke(
                    app,
                    ["monitor", "test-owner", "--output", tmpdir, "--format", "markdown"],
                )

                assert result.exit_code == 0
                assert "Successfully monitored 1 repositories" in result.stdout
                assert "0 open PRs" in result.stdout

                # Check output file was created
                assert (Path(tmpdir) / "report.md").exists()

    def test_monitor_toon_format_only(self, mock_repository):
        """Test monitor with TOON format only."""
        with patch("gh_monitor.cli.ProjectMonitor") as MockMonitor:
            mock_instance = MagicMock()
            mock_instance.collect_all_data.return_value = [mock_repository]
            MockMonitor.return_value = mock_instance

            with tempfile.TemporaryDirectory() as tmpdir:
                result = runner.invoke(
                    app,
                    ["monitor", "test-owner", "--output", tmpdir, "--format", "toon"],
                )

                assert result.exit_code == 0
                assert (Path(tmpdir) / "report.toon").exists()
                assert not (Path(tmpdir) / "report.md").exists()
                assert not (Path(tmpdir) / "report.html").exists()

    def test_monitor_markdown_format_only(self, mock_repository):
        """Test monitor with Markdown format only."""
        with patch("gh_monitor.cli.ProjectMonitor") as MockMonitor:
            mock_instance = MagicMock()
            mock_instance.collect_all_data.return_value = [mock_repository]
            MockMonitor.return_value = mock_instance

            with tempfile.TemporaryDirectory() as tmpdir:
                result = runner.invoke(
                    app,
                    [
                        "monitor",
                        "test-owner",
                        "--output",
                        tmpdir,
                        "--format",
                        "markdown",
                    ],
                )

                assert result.exit_code == 0
                assert (Path(tmpdir) / "report.md").exists()
                assert not (Path(tmpdir) / "report.toon").exists()

    def test_monitor_html_format_only(self, mock_repository):
        """Test monitor with HTML format only."""
        with patch("gh_monitor.cli.ProjectMonitor") as MockMonitor:
            mock_instance = MagicMock()
            mock_instance.collect_all_data.return_value = [mock_repository]
            MockMonitor.return_value = mock_instance

            with tempfile.TemporaryDirectory() as tmpdir:
                result = runner.invoke(
                    app,
                    ["monitor", "test-owner", "--output", tmpdir, "--format", "html"],
                )

                assert result.exit_code == 0
                assert (Path(tmpdir) / "report.html").exists()
                assert not (Path(tmpdir) / "report.toon").exists()

    def test_monitor_custom_days(self, mock_repository):
        """Test monitor with custom days parameter."""
        with patch("gh_monitor.cli.ProjectMonitor") as MockMonitor:
            mock_instance = MagicMock()
            mock_instance.collect_all_data.return_value = [mock_repository]
            MockMonitor.return_value = mock_instance

            with tempfile.TemporaryDirectory() as tmpdir:
                result = runner.invoke(
                    app,
                    [
                        "monitor",
                        "test-owner",
                        "--output",
                        tmpdir,
                        "--days",
                        "60",
                        "--format",
                        "markdown",
                    ],
                )

                assert result.exit_code == 0
                MockMonitor.assert_called_once_with("test-owner", 60, False)

    def test_monitor_verbose_mode(self, mock_repository):
        """Test monitor with verbose flag."""
        with patch("gh_monitor.cli.ProjectMonitor") as MockMonitor:
            mock_instance = MagicMock()
            mock_instance.collect_all_data.return_value = [mock_repository]
            MockMonitor.return_value = mock_instance

            with tempfile.TemporaryDirectory() as tmpdir:
                result = runner.invoke(
                    app,
                    [
                        "monitor",
                        "test-owner",
                        "--output",
                        tmpdir,
                        "--verbose",
                        "--format",
                        "markdown",
                    ],
                )

                assert result.exit_code == 0
                MockMonitor.assert_called_once_with("test-owner", 90, True)

    def test_monitor_creates_output_directory(self, mock_repository):
        """Test that monitor creates output directory if it doesn't exist."""
        with patch("gh_monitor.cli.ProjectMonitor") as MockMonitor:
            mock_instance = MagicMock()
            mock_instance.collect_all_data.return_value = [mock_repository]
            MockMonitor.return_value = mock_instance

            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir) / "nested" / "output"
                result = runner.invoke(
                    app,
                    [
                        "monitor",
                        "test-owner",
                        "--output",
                        str(output_dir),
                        "--format",
                        "markdown",
                    ],
                )

                assert result.exit_code == 0
                assert output_dir.exists()


class TestErrorHandling:
    """Tests for error handling in CLI."""

    def test_monitor_exception_handling(self):
        """Test CLI handles exceptions gracefully."""
        with patch("gh_monitor.cli.ProjectMonitor") as MockMonitor:
            mock_instance = MagicMock()
            mock_instance.collect_all_data.side_effect = Exception("Test error")
            MockMonitor.return_value = mock_instance

            with tempfile.TemporaryDirectory() as tmpdir:
                result = runner.invoke(
                    app,
                    ["monitor", "test-owner", "--output", tmpdir, "--format", "markdown"],
                )

                assert result.exit_code == 1
                # Error is printed to stderr (check output or exception)
                output = result.output + (
                    result.stderr if hasattr(result, "stderr") and result.stderr else ""
                )
                assert "Error" in output or "Test error" in str(result.exception)

    def test_monitor_exception_with_verbose(self):
        """Test CLI shows traceback with verbose flag on error."""
        with patch("gh_monitor.cli.ProjectMonitor") as MockMonitor:
            mock_instance = MagicMock()
            mock_instance.collect_all_data.side_effect = Exception("Test error")
            MockMonitor.return_value = mock_instance

            with tempfile.TemporaryDirectory() as tmpdir:
                result = runner.invoke(
                    app,
                    [
                        "monitor",
                        "test-owner",
                        "--output",
                        tmpdir,
                        "--verbose",
                        "--format",
                        "markdown",
                    ],
                )

                assert result.exit_code == 1
                # Traceback is printed to stderr (check output or exception)
                output = result.output + (
                    result.stderr if hasattr(result, "stderr") and result.stderr else ""
                )
                assert "Traceback" in output or "Test error" in str(result.exception)


class TestPublishToGhPages:
    """Tests for publishing reports to the gh-pages branch."""

    def _init_repo(self, path: Path, remote: Path) -> None:
        """Initialize a git repo with an initial commit and a bare origin remote."""
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }

        subprocess.run(
            ["git", "init", "--bare", str(remote)], check=True, env=env, capture_output=True
        )

        def git(*args: str) -> None:
            subprocess.run(["git", *args], cwd=path, check=True, env=env, capture_output=True)

        git("init", "-b", "main")
        git("remote", "add", "origin", str(remote))
        (path / "README.md").write_text("initial")
        git("add", "README.md")
        git("commit", "-m", "initial")

    def test_publishes_html_and_markdown(self, tmp_path, monkeypatch):
        """HTML is published as index.html, Markdown as index.md and llms.txt."""
        repo = tmp_path / "repo"
        repo.mkdir()
        self._init_repo(repo, tmp_path / "remote.git")

        html_path = tmp_path / "report.html"
        html_path.write_text("<html><body>report</body></html>")
        markdown_path = tmp_path / "report.md"
        markdown_path.write_text("# Report\n\nbot-friendly content")

        monkeypatch.chdir(repo)
        _publish_to_gh_pages(html_path, markdown_path)

        # Inspect the gh-pages branch contents without checking it out
        def show(filename: str) -> str:
            return subprocess.run(
                ["git", "show", f"gh-pages:{filename}"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout

        assert "report" in show("index.html")
        assert "bot-friendly content" in show("index.md")
        assert "bot-friendly content" in show("llms.txt")

    def test_publishes_html_only_when_no_markdown(self, tmp_path, monkeypatch):
        """Markdown files are skipped when no Markdown report is available."""
        repo = tmp_path / "repo"
        repo.mkdir()
        self._init_repo(repo, tmp_path / "remote.git")

        html_path = tmp_path / "report.html"
        html_path.write_text("<html><body>report</body></html>")

        monkeypatch.chdir(repo)
        _publish_to_gh_pages(html_path, markdown_path=None)

        tracked = subprocess.run(
            ["git", "ls-tree", "--name-only", "gh-pages"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()

        assert "index.html" in tracked
        assert "index.md" not in tracked
        assert "llms.txt" not in tracked


class TestHelpCommand:
    """Tests for help output."""

    def test_help_output(self):
        """Test help shows available commands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "monitor" in result.stdout.lower()
        assert "version" in result.stdout.lower()

    def test_monitor_help(self):
        """Test monitor command help."""
        result = runner.invoke(app, ["monitor", "--help"])
        assert result.exit_code == 0
        output = strip_ansi(result.stdout)
        assert "--output" in output
        assert "--days" in output
        assert "--format" in output
        assert "--verbose" in output
