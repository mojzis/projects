"""Tests for data models."""

from datetime import datetime

from gh_monitor.models import CIStatus, Commit, MonitorReport, Repository


def test_commit_to_dict():
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


def test_monitor_report_aggregation():
    """Test report aggregation."""
    repo = Repository(
        name="test-repo",
        owner="test-owner",
        full_name="test-owner/test-repo",
        url="https://github.com/test-owner/test-repo",
        last_commit=None,
        open_prs=[],
        branches_without_prs=["feature-1", "feature-2"],
        github_pages_enabled=False,
        github_pages_url=None,
        ci_status=CIStatus.SUCCESS,
        ci_recent_runs=[],
        ci_success_rate=1.0,
        last_updated=datetime.now(),
    )

    report = MonitorReport(
        generated_at=datetime.now(), scan_period_days=30, repositories=[repo]
    )

    assert report.total_repositories == 1
    assert report.total_branches_without_prs == 2
