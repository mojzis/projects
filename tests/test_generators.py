"""Tests for report generators."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from gh_monitor.generators import (
    generate_html_report,
    generate_markdown_report,
    generate_toon_report,
)
from gh_monitor.models import (
    CIRun,
    CIStatus,
    Commit,
    MonitorReport,
    PullRequest,
    Repository,
)


@pytest.fixture
def sample_commit():
    """Create a sample commit."""
    return Commit(
        sha="abc123def456",
        message="Fix critical bug",
        author="John Doe",
        date=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_pr():
    """Create a sample PR."""
    return PullRequest(
        number=42,
        title="Add new feature",
        created_at=datetime(2025, 1, 10, 10, 0, 0, tzinfo=timezone.utc),
        author="janedoe",
        age_days=5,
        url="https://github.com/owner/repo/pull/42",
    )


@pytest.fixture
def sample_ci_run():
    """Create a sample CI run."""
    return CIRun(
        name="Build",
        status="completed",
        conclusion="success",
        created_at=datetime(2025, 1, 15, 8, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_repository(sample_commit, sample_pr, sample_ci_run):
    """Create a sample repository."""
    return Repository(
        name="test-repo",
        owner="test-owner",
        full_name="test-owner/test-repo",
        url="https://github.com/test-owner/test-repo",
        last_commit=sample_commit,
        open_prs=[sample_pr],
        branches_without_prs=["feature-x", "feature-y"],
        github_pages_enabled=True,
        github_pages_url="https://test-owner.github.io/test-repo",
        ci_status=CIStatus.SUCCESS,
        ci_recent_runs=[sample_ci_run],
        ci_success_rate=0.95,
        last_updated=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        stars=100,
        forks=25,
        open_issues=5,
        primary_language="Python",
    )


@pytest.fixture
def sample_report(sample_repository):
    """Create a sample monitor report."""
    return MonitorReport(
        generated_at=datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc),
        scan_period_days=30,
        repositories=[sample_repository],
    )


@pytest.fixture
def empty_report():
    """Create an empty monitor report."""
    return MonitorReport(
        generated_at=datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc),
        scan_period_days=30,
        repositories=[],
    )


class TestToonGenerator:
    """Tests for TOON format generator."""

    @pytest.mark.skip(reason="toon-format encoder not yet implemented")
    def test_generate_toon_report(self, sample_report):
        """Test TOON report generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.toon"
            generate_toon_report(sample_report, output_path)

            assert output_path.exists()
            content = output_path.read_text()
            assert len(content) > 0
            # TOON format should contain report data
            assert "test-repo" in content or "test_repo" in content.lower()

    @pytest.mark.skip(reason="toon-format encoder not yet implemented")
    def test_generate_toon_report_empty(self, empty_report):
        """Test TOON report with empty repositories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.toon"
            generate_toon_report(empty_report, output_path)

            assert output_path.exists()
            content = output_path.read_text()
            assert len(content) > 0


class TestMarkdownGenerator:
    """Tests for Markdown format generator."""

    def test_generate_markdown_report(self, sample_report):
        """Test Markdown report generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.md"
            generate_markdown_report(sample_report, output_path)

            assert output_path.exists()
            content = output_path.read_text()

            # Check report header
            assert "GitHub Project Monitor Report" in content
            assert "Last 30 days" in content

            # Check repository info
            assert "test-owner/test-repo" in content
            assert "Python" in content
            assert "100" in content  # stars

            # Check PR info
            assert "#42" in content
            assert "Add new feature" in content

            # Check branches
            assert "feature-x" in content
            assert "feature-y" in content

            # Check CI status
            assert "PASS" in content or "success" in content.lower()

    def test_generate_markdown_report_empty(self, empty_report):
        """Test Markdown report with empty repositories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.md"
            generate_markdown_report(empty_report, output_path)

            assert output_path.exists()
            content = output_path.read_text()
            assert "GitHub Project Monitor Report" in content
            assert "Total Repositories:** 0" in content

    def test_generate_markdown_report_no_commit(self):
        """Test Markdown report with repository without commit."""
        repo = Repository(
            name="empty-repo",
            owner="owner",
            full_name="owner/empty-repo",
            url="https://github.com/owner/empty-repo",
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
        report = MonitorReport(
            generated_at=datetime.now(timezone.utc),
            scan_period_days=30,
            repositories=[repo],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.md"
            generate_markdown_report(report, output_path)

            assert output_path.exists()
            content = output_path.read_text()
            assert "No commit information available" in content

    def test_generate_markdown_report_no_prs(self):
        """Test Markdown report with repository without PRs."""
        repo = Repository(
            name="no-prs-repo",
            owner="owner",
            full_name="owner/no-prs-repo",
            url="https://github.com/owner/no-prs-repo",
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
        report = MonitorReport(
            generated_at=datetime.now(timezone.utc),
            scan_period_days=30,
            repositories=[repo],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.md"
            generate_markdown_report(report, output_path)

            content = output_path.read_text()
            assert "No open pull requests" in content


class TestHTMLGenerator:
    """Tests for HTML format generator."""

    def test_generate_html_report(self, sample_report):
        """Test HTML report generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            generate_html_report(sample_report, output_path)

            assert output_path.exists()
            content = output_path.read_text()

            # Check HTML structure
            assert "<!DOCTYPE html>" in content
            assert "<html" in content
            assert "</html>" in content
            assert "GitHub Project Monitor Report" in content

            # Check repository info
            assert "test-owner/test-repo" in content
            assert "Python" in content

            # Check PR info
            assert "#42" in content

    def test_generate_html_report_empty(self, empty_report):
        """Test HTML report with empty repositories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            generate_html_report(empty_report, output_path)

            assert output_path.exists()
            content = output_path.read_text()
            assert "<!DOCTYPE html>" in content

    def test_generate_html_report_ci_status(self):
        """Test HTML report shows correct CI status badges."""
        repos = [
            Repository(
                name="passing-repo",
                owner="owner",
                full_name="owner/passing-repo",
                url="https://github.com/owner/passing-repo",
                last_commit=None,
                open_prs=[],
                branches_without_prs=[],
                github_pages_enabled=False,
                github_pages_url=None,
                ci_status=CIStatus.SUCCESS,
                ci_recent_runs=[],
                ci_success_rate=1.0,
                last_updated=datetime.now(timezone.utc),
            ),
            Repository(
                name="failing-repo",
                owner="owner",
                full_name="owner/failing-repo",
                url="https://github.com/owner/failing-repo",
                last_commit=None,
                open_prs=[],
                branches_without_prs=[],
                github_pages_enabled=False,
                github_pages_url=None,
                ci_status=CIStatus.FAILURE,
                ci_recent_runs=[],
                ci_success_rate=0.0,
                last_updated=datetime.now(timezone.utc),
            ),
        ]
        report = MonitorReport(
            generated_at=datetime.now(timezone.utc),
            scan_period_days=30,
            repositories=repos,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            generate_html_report(report, output_path)

            content = output_path.read_text()
            assert "PASS" in content
            assert "FAIL" in content


class TestMultipleRepositories:
    """Tests for reports with multiple repositories."""

    def test_markdown_multiple_repos(self, sample_repository):
        """Test Markdown with multiple repositories."""
        repo2 = Repository(
            name="another-repo",
            owner="test-owner",
            full_name="test-owner/another-repo",
            url="https://github.com/test-owner/another-repo",
            last_commit=None,
            open_prs=[],
            branches_without_prs=["dev"],
            github_pages_enabled=False,
            github_pages_url=None,
            ci_status=CIStatus.FAILURE,
            ci_recent_runs=[],
            ci_success_rate=0.5,
            last_updated=datetime.now(timezone.utc),
            primary_language="JavaScript",
        )

        report = MonitorReport(
            generated_at=datetime.now(timezone.utc),
            scan_period_days=30,
            repositories=[sample_repository, repo2],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.md"
            generate_markdown_report(report, output_path)

            content = output_path.read_text()
            assert "test-repo" in content
            assert "another-repo" in content
            assert "Python" in content
            assert "JavaScript" in content
