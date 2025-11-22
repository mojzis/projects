"""Simple list generator - outputs repository names only."""

from pathlib import Path

from ..models import MonitorReport


def generate_list_report(report: MonitorReport, output_path: Path) -> None:
    """Generate a plain text list of repository names."""
    lines = [r.name for r in report.repositories]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
