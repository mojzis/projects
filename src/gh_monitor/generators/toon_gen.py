"""TOON format report generator."""

from pathlib import Path

from toon_format import encode

from ..models import MonitorReport


def generate_toon_report(report: MonitorReport, output_path: Path) -> None:
    """Generate TOON format report from MonitorReport."""
    data = report.to_dict()
    toon_str = encode(data)
    output_path.write_text(toon_str, encoding="utf-8")
