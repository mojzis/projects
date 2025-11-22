"""TOON format report generator."""

import json
import warnings
from pathlib import Path

from ..models import MonitorReport


def generate_toon_report(report: MonitorReport, output_path: Path) -> None:
    """Generate TOON format report from MonitorReport.

    Falls back to JSON if the TOON encoder is not implemented.
    """
    data = report.to_dict()

    try:
        from toon_format import encode

        toon_str = encode(data)
    except NotImplementedError:
        # TOON encoder not yet implemented, fall back to JSON
        warnings.warn(
            "TOON encoder not implemented, falling back to JSON format",
            UserWarning,
            stacklevel=2,
        )
        toon_str = json.dumps(data, indent=2, default=str)

    output_path.write_text(toon_str, encoding="utf-8")
