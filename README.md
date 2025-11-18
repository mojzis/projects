# GitHub Project Monitor

Monitor GitHub project status using gh CLI with TOON, Markdown, and HTML output.

## Features

- Monitor repositories with recent activity (last N days)
- Track open pull requests and their age
- Identify branches without PRs
- Check CI/CD status and success rates
- Detect GitHub Pages enabled repositories
- Generate reports in three formats:
  - **TOON**: Token-efficient format for LLM consumption
  - **Markdown**: Human-readable reports
  - **HTML**: Clean web-based visualization

## Requirements

- Python 3.11+
- GitHub CLI (`gh`) installed and authenticated
- uv package manager (recommended)

## Installation

```bash
# Install with uv
uv sync

# Or install globally
uv build
uv pip install dist/gh_project_monitor-0.1.0-py3-none-any.whl
```

## Usage

```bash
# Monitor organization (all formats)
uv run gh-monitor myorg --days 30 --output reports/

# Generate specific format
uv run gh-monitor myorg --format toon --output reports/
uv run gh-monitor myorg --format markdown --output reports/
uv run gh-monitor myorg --format html --output reports/

# If installed globally
gh-monitor myorg --days 7
```

## CLI Options

- `owner`: GitHub organization or user (required)
- `--output, -o`: Output directory for reports (default: reports/)
- `--days, -d`: Monitor repos changed in last N days (default: 30)
- `--format, -f`: Output format: toon, markdown, html, or all (default: all)
- `--verbose, -v`: Enable verbose output

## Development

```bash
# Run tests
uv run pytest

# Format code
uv run ruff format .

# Lint code
uv run ruff check .
```

## Output Examples

### TOON Format
Compact, LLM-optimized structured data (30-60% token reduction vs JSON).

### Markdown Format
Human-readable reports with tables, stats, and links.

### HTML Format
Clean, minimal white design for web viewing.

## License

MIT
