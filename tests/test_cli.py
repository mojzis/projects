"""Tests for CLI interface."""

import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gh_monitor.cli import app
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
        """Test monitor with TOON format only (falls back to JSON)."""
        import warnings

        with patch("gh_monitor.cli.ProjectMonitor") as MockMonitor:
            mock_instance = MagicMock()
            mock_instance.collect_all_data.return_value = [mock_repository]
            MockMonitor.return_value = mock_instance

            with tempfile.TemporaryDirectory() as tmpdir:
                # Suppress the expected warning about TOON encoder
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
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
                MockMonitor.assert_called_once_with("test-owner", 30, True)

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
