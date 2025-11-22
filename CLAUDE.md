# CLAUDE.md - Project Context for Claude Code

## Project Overview

**Name:** GitHub Project Monitor (`gh-project-monitor`)
**Version:** 0.1.0
**Python:** >=3.11

A CLI tool that monitors GitHub project status using the GitHub CLI (`gh`) and generates reports in TOON (token-optimized), Markdown, and HTML formats. Designed for tracking repository activity, pull requests, CI/CD status, and GitHub Pages across organizations.

## Quick Start

```bash
# Install dependencies
uv sync

# Run the tool
uv run gh-monitor <owner> --days 30 --format all --output reports/

# Run tests
uv run pytest

# Lint and format
uv run ruff check .
uv run ruff format .
```

## Project Structure

```
gh_monitor/
├── __init__.py           # Package init, exports version
├── __main__.py           # Entry point for `python -m gh_monitor`
├── cli.py                # Typer CLI interface (main command: monitor)
├── collector.py          # GitHub CLI wrapper (subprocess-based)
├── monitor.py            # Orchestration logic for data collection
├── models.py             # Type-safe dataclasses (Commit, PR, Repository, etc.)
├── generators/
│   ├── __init__.py       # Exports all generators
│   ├── toon_gen.py       # TOON format output (uses toon_format library)
│   ├── markdown_gen.py   # Markdown output (Jinja2 templates)
│   └── html_gen.py       # HTML output (Jinja2 templates)
├── templates/
│   └── report.md         # Jinja2 markdown template
└── py.typed              # PEP 561 marker
tests/
├── __init__.py
└── test_models.py        # Basic model tests
plans/
└── gh-project-monitor-plan.md  # Original implementation plan
```

## Architecture

```
CLI (Typer) -> ProjectMonitor -> GitHubCollector -> gh CLI (subprocess)
                   |
                   v
              Data Models (dataclasses)
                   |
                   v
              Report Generators (TOON/MD/HTML)
```

### Key Components

1. **GitHubCollector** (`collector.py`): Wraps `gh` CLI commands via subprocess
   - `get_repositories()`: List repos filtered by activity date
   - `get_last_commit()`: Fetch latest commit on main/master
   - `get_open_prs()`: List open pull requests
   - `get_branches()` / `get_pr_branches()`: Branch tracking
   - `get_github_pages()`: Pages status detection
   - `get_ci_runs()`: CI/CD workflow runs
   - `get_repo_details()`: Stars, forks, issues, language

2. **ProjectMonitor** (`monitor.py`): Orchestrates collection across repos
   - `collect_all_data()`: Main loop with progress callback
   - `_collect_repo_data()`: Per-repository data assembly

3. **Data Models** (`models.py`): Type-safe dataclasses
   - `CIStatus` (enum): success/failure/pending/no_ci/unknown
   - `Commit`: sha, message, author, date
   - `PullRequest`: number, title, author, age_days, url
   - `CIRun`: name, status, conclusion, created_at
   - `Repository`: Full repo metrics with nested models
   - `MonitorReport`: Aggregated report with auto-calculated totals

4. **Report Generators** (`generators/`):
   - `generate_toon_report()`: Uses `toon_format.encode()`
   - `generate_markdown_report()`: Jinja2 with `report.md` template
   - `generate_html_report()`: Jinja2 with `report.html` template

## CLI Interface

```bash
gh-monitor OWNER [OPTIONS]

Arguments:
  OWNER    GitHub organization or user (required)

Options:
  -o, --output PATH    Output directory (default: reports/)
  -d, --days INT       Monitor repos changed in last N days (1-365, default: 30)
  -f, --format TEXT    Output format: toon, markdown, html, all (default: all)
  -v, --verbose        Enable verbose output with tracebacks
```

## Dependencies

**Runtime:**
- typer>=0.12.0 - CLI framework
- toon-format>=0.1.0 - Token-efficient output format
- jinja2>=3.1.0 - Template rendering
- rich>=13.7.0 - Terminal output and progress bars

**Development:**
- pytest>=8.0.0 - Testing
- pytest-cov>=4.1.0 - Coverage
- ruff>=0.3.0 - Linting and formatting

**External:**
- GitHub CLI (`gh`) must be installed and authenticated

## Code Style

- **Line length:** 100 characters
- **Linter:** Ruff with rules E, F, B, I, N, UP, S, C90
- **Type hints:** Full annotations throughout (Python 3.11+ union syntax)
- **Format:** Run `uv run ruff format .` before commits

## Testing

```bash
uv run pytest                    # Run all tests
uv run pytest --cov=gh_monitor   # With coverage
uv run pytest -v                 # Verbose output
```

Current test coverage is minimal - see "What's Missing" section.

---

## Implementation Status

### Fully Implemented

| Component | File | Status |
|-----------|------|--------|
| CLI interface | `cli.py` | Complete |
| GitHub collector | `collector.py` | Complete |
| Monitor orchestration | `monitor.py` | Complete |
| Data models | `models.py` | Complete |
| TOON generator | `generators/toon_gen.py` | Complete |
| Markdown generator | `generators/markdown_gen.py` | Complete |
| HTML generator code | `generators/html_gen.py` | Complete |
| Markdown template | `templates/report.md` | Complete |
| README | `README.md` | Complete |
| Package config | `pyproject.toml` | Complete |

### What's Missing

| Item | Priority | Notes |
|------|----------|-------|
| **HTML template** | HIGH | `templates/report.html` is missing - `html_gen.py:14` references it but file doesn't exist. HTML generation will fail. |
| **Comprehensive tests** | HIGH | Only 2 basic model tests exist. Missing: test_cli.py, test_collector.py, test_generators.py, conftest.py with fixtures |
| **CI/CD workflow** | MEDIUM | No `.github/workflows/ci.yml` - mentioned in plan but not implemented |
| **Rate limiting** | LOW | No explicit handling of GitHub API rate limits |
| **Retry logic** | LOW | No retry mechanism for transient failures |
| **conftest.py** | MEDIUM | No shared fixtures for tests |

### Known Issues

1. **HTML generation broken**: Will raise `TemplateNotFound` for `report.html`
2. **No integration tests**: Collector tests would need mocking of subprocess calls
3. **Subprocess security**: Uses `subprocess.run` with shell=False (safe), but S603/S607 are explicitly ignored in ruff config

## GitHub CLI Commands Used

The collector executes these `gh` commands:

```bash
# List repositories
gh repo list OWNER --json name,pushedAt,updatedAt,stargazerCount,forkCount,url --limit 1000

# Last commit (tries main, falls back to master)
gh api repos/OWNER/REPO/commits/main

# Open PRs
gh pr list --repo OWNER/REPO --state open --json number,title,createdAt,author,url --limit 100

# All branches
gh api repos/OWNER/REPO/branches --paginate

# Branches with PRs (for orphan detection)
gh pr list --repo OWNER/REPO --state all --json headRefName --limit 1000

# GitHub Pages status
gh api repos/OWNER/REPO/pages

# CI runs
gh run list --repo OWNER/REPO --limit 20 --json status,conclusion,name,createdAt

# Repo details
gh repo view OWNER/REPO --json stargazerCount,forkCount,openIssues,primaryLanguage
```

## Output Formats

### TOON Format
Token-optimized notation (30-60% more efficient than JSON for LLM consumption). Generated via `toon_format.encode()`.

### Markdown Format
Human-readable report using Jinja2 template at `templates/report.md`. Includes:
- Summary statistics table
- Per-repository sections with commits, PRs, branches, CI status
- Repository overview grid

### HTML Format
Clean web visualization (template missing - needs `templates/report.html`).

## Common Tasks

### Adding a new data field to Repository

1. Add field to `Repository` dataclass in `models.py`
2. Update `to_dict()` method in `Repository`
3. Collect the data in `monitor.py:_collect_repo_data()`
4. Add to template context in `markdown_gen.py` and `html_gen.py`
5. Update Jinja2 templates to display the field

### Adding a new CLI option

1. Add parameter to `monitor()` function in `cli.py`
2. Use `typer.Option()` annotation
3. Pass to `ProjectMonitor` or use in report generation

### Writing tests

Tests go in `tests/` directory. Use pytest fixtures for common setup:

```python
# tests/conftest.py (needs to be created)
import pytest
from datetime import datetime
from gh_monitor.models import Repository, CIStatus

@pytest.fixture
def sample_repository():
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
        ci_status=CIStatus.NO_CI,
        ci_recent_runs=[],
        ci_success_rate=0.0,
        last_updated=datetime.now(),
    )
```

## Notes for Development

- **Package layout**: Flat layout (gh_monitor/ at root, not src/gh_monitor/)
- **Entry point**: `gh-monitor` command defined in `pyproject.toml`
- **Verbose mode**: Use `-v` flag to see full tracebacks on errors
- **Progress tracking**: CLI uses Rich progress bars during collection
- **Error handling**: GitHubCLIError exception for gh command failures
