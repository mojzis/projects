"""Markdown report generator."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ..models import MonitorReport, Repository


def _get_last_failure(repo: Repository) -> str | None:
    """Get the name of the most recent failed CI run."""
    for run in repo.ci_recent_runs:
        if run.conclusion == "failure":
            return run.name
    return None


def generate_markdown_report(report: MonitorReport, output_path: Path) -> None:
    """Generate Markdown report using Jinja2 template."""
    template_dir = Path(__file__).parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("report.md")

    markdown = template.render(
        timestamp=report.generated_at.strftime("%Y-%m-%d %H:%M:%S"),
        scan_days=report.scan_period_days,
        total_repos=report.total_repositories,
        total_prs=report.total_open_prs,
        repositories=[
            {
                "name": r.name,
                "url": r.url,
                "language": r.primary_language,
                "stars": r.stars,
                "open_issues": r.open_issues,
                "last_commit": r.last_commit,
                "open_prs": r.open_prs,
                "branches_without_prs": r.branches_without_prs,
                "github_pages_enabled": r.github_pages_enabled,
                "github_pages_url": r.github_pages_url,
                "ci_status": r.ci_status.value,
                "ci_last_failure": _get_last_failure(r),
            }
            for r in report.repositories
        ],
    )

    output_path.write_text(markdown, encoding="utf-8")
