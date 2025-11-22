"""Report generators for TOON, Markdown, and HTML formats."""

from .html_gen import generate_html_report
from .markdown_gen import generate_markdown_report
from .toon_gen import generate_toon_report

__all__ = ["generate_toon_report", "generate_markdown_report", "generate_html_report"]
