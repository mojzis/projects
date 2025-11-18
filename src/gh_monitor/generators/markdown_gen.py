"""Markdown report generator."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ..models import CIStatus, MonitorReport


def generate_markdown_report(report: MonitorReport, output_path: Path) -> None:
    """Generate Markdown report using Jinja2 template."""
    template_dir = Path(__file__).parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("report.md")

    # Calculate summary stats
    passing_ci = sum(1 for r in report.repositories if r.ci_status == CIStatus.SUCCESS)
    failing_ci = sum(1 for r in report.repositories if r.ci_status == CIStatus.FAILURE)
    pages_enabled = sum(1 for r in report.repositories if r.github_pages_enabled)

    markdown = template.render(
        timestamp=report.generated_at.strftime("%Y-%m-%d %H:%M:%S"),
        scan_days=report.scan_period_days,
        total_repos=report.total_repositories,
        total_prs=report.total_open_prs,
        total_branches=report.total_branches_without_prs,
        passing_ci=passing_ci,
        failing_ci=failing_ci,
        pages_enabled=pages_enabled,
        repositories=[
            {
                "name": r.name,
                "owner": r.owner,
                "full_name": r.full_name,
                "url": r.url,
                "language": r.primary_language,
                "stars": r.stars,
                "forks": r.forks,
                "open_issues": r.open_issues,
                "last_commit": r.last_commit,
                "open_prs": r.open_prs,
                "branches_without_prs": r.branches_without_prs,
                "github_pages_enabled": r.github_pages_enabled,
                "github_pages_url": r.github_pages_url,
                "ci_status": r.ci_status.value,
                "ci_success_rate": r.ci_success_rate,
                "ci_recent_runs": r.ci_recent_runs,
                "pr_count": len(r.open_prs),
                "branch_without_pr_count": len(r.branches_without_prs),
            }
            for r in report.repositories
        ],
    )

    output_path.write_text(markdown, encoding="utf-8")
