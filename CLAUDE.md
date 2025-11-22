# CLAUDE.md - Project Context for Claude Code

## Project Overview

**Name:** GitHub Project Monitor (`gh-project-monitor`)
**Version:** 0.1.0
**Python:** >=3.11

A CLI tool that monitors GitHub project status using the GitHub CLI (`gh`) and generates reports in TOON (token-optimized), Markdown, and HTML formats. Also provides repository synchronization to keep local clones up-to-date.

## Quick Start

```bash
# Install dependencies
uv sync

# Monitor repositories and generate reports
uv run gh-monitor monitor <owner> --days 30 --format all --output reports/

# Sync repositories to local directory
uv run gh-monitor sync <owner> --dir ~/git

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
├── cli.py                # Typer CLI interface (commands: monitor, sync, version)
├── collector.py          # GitHub CLI wrapper (subprocess-based)
├── monitor.py            # Orchestration logic for data collection
├── syncer.py             # Git repository synchronization
├── models.py             # Type-safe dataclasses (Commit, PR, Repository, Sync*, etc.)
├── generators/
│   ├── __init__.py       # Exports all generators
│   ├── toon_gen.py       # TOON format output (uses toon_format library)
│   ├── markdown_gen.py   # Markdown output (Jinja2 templates)
│   └── html_gen.py       # HTML output (Jinja2 templates)
├── templates/
│   ├── report.md         # Jinja2 markdown template
│   └── report.html       # Jinja2 HTML template
└── py.typed              # PEP 561 marker

tests/
├── __init__.py
├── test_cli.py           # CLI command tests
├── test_collector.py     # GitHub collector tests
├── test_generators.py    # Report generator tests
├── test_models.py        # Data model tests
├── test_monitor.py       # Monitor orchestration tests
└── test_syncer.py        # Git syncer tests

.github/
└── workflows/
    └── ci.yml            # GitHub Actions CI pipeline

plans/
└── gh-project-monitor-plan.md  # Original implementation plan
```

## Architecture

```
CLI (Typer)
    ├── monitor command -> ProjectMonitor -> GitHubCollector -> gh CLI
    │                           |
    │                           v
    │                      Data Models -> Report Generators (TOON/MD/HTML)
    │
    └── sync command -> GitSyncer -> git CLI (clone/pull)
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

3. **GitSyncer** (`syncer.py`): Syncs GitHub repos with local directory
   - `sync_all()`: Clone missing repos, pull existing clean repos
   - `_clone_repo()`: Clone a new repository
   - `_pull_repo()`: Pull updates (skips dirty repos)
   - `_is_git_clean()`: Check for uncommitted changes
   - `_needs_pull()`: Check if behind remote

4. **Data Models** (`models.py`): Type-safe dataclasses
   - `CIStatus` (enum): success/failure/pending/no_ci/unknown
   - `Commit`: sha, message, author, date
   - `PullRequest`: number, title, author, age_days, url
   - `CIRun`: name, status, conclusion, created_at
   - `Repository`: Full repo metrics with nested models
   - `MonitorReport`: Aggregated report with auto-calculated totals
   - `SyncAction` (enum): cloned/pulled/skipped_dirty/skipped_error/already_current
   - `SyncResult`: Single repo sync result
   - `SyncReport`: Aggregated sync summary

5. **Report Generators** (`generators/`):
   - `generate_toon_report()`: Uses `toon_format.encode()`
   - `generate_markdown_report()`: Jinja2 with `report.md` template
   - `generate_html_report()`: Jinja2 with `report.html` template

## CLI Interface

### Monitor Command
```bash
gh-monitor monitor OWNER [OPTIONS]

Arguments:
  OWNER    GitHub organization or user (required)

Options:
  -o, --output PATH    Output directory (default: reports/)
  -d, --days INT       Monitor repos changed in last N days (1-365, default: 30)
  -f, --format TEXT    Output format: toon, markdown, html, all (default: all)
  -v, --verbose        Enable verbose output with tracebacks
```

### Sync Command
```bash
gh-monitor sync OWNER [OPTIONS]

Arguments:
  OWNER    GitHub organization or user to sync (required)

Options:
  -d, --dir PATH       Local git directory (default: ~/git)
  -v, --verbose        Enable verbose output
```

Sync behavior:
- Missing repos are cloned (using SSH URL)
- Existing clean repos are pulled
- Dirty repos (uncommitted changes) are skipped
- Reports summary of actions taken

### Version Command
```bash
gh-monitor version
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
- Git must be installed (for sync command)

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
uv run pytest tests/test_cli.py  # Single test file
```

Test files:
- `test_cli.py` - CLI command tests with mocked dependencies
- `test_collector.py` - GitHub CLI wrapper tests with subprocess mocking
- `test_generators.py` - Report generator tests (TOON, Markdown, HTML)
- `test_models.py` - Data model serialization and aggregation tests
- `test_monitor.py` - Monitor orchestration tests
- `test_syncer.py` - Git sync operation tests

## CI/CD

GitHub Actions workflow (`.github/workflows/ci.yml`):
- Runs on push/PR to main/master
- Tests on Python 3.11 and 3.12
- Linting with ruff
- Format checking
- Test coverage with codecov upload

## GitHub CLI Commands Used

The collector executes these `gh` commands:

```bash
# List repositories
gh repo list OWNER --json name,pushedAt,updatedAt,stargazerCount,forkCount,url --limit 1000

# List repos for sync (includes SSH URL)
gh repo list OWNER --json name,url,sshUrl --limit 1000

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
Clean web visualization using Jinja2 template at `templates/report.html`. Features:
- GitHub-style CSS styling
- Summary statistics dashboard with large numbers
- Repository cards with all metrics
- Status badges (pass/fail/pending)
- Responsive design

## Common Tasks

### Adding a new data field to Repository

1. Add field to `Repository` dataclass in `models.py`
2. Update `to_dict()` method in `Repository`
3. Collect the data in `monitor.py:_collect_repo_data()`
4. Add to template context in `markdown_gen.py` and `html_gen.py`
5. Update Jinja2 templates to display the field
6. Add tests in `test_models.py`

### Adding a new CLI command

1. Add command function with `@app.command()` decorator in `cli.py`
2. Use `typer.Argument()` and `typer.Option()` annotations
3. Add tests in `test_cli.py`

### Adding a new report format

1. Create new generator in `generators/` directory
2. Export from `generators/__init__.py`
3. Add format option handling in `cli.py:_generate_reports()`
4. Add template if needed in `templates/`
5. Add tests in `test_generators.py`

## Notes for Development

- **Package layout**: Flat layout (gh_monitor/ at root, not src/gh_monitor/)
- **Entry point**: `gh-monitor` command defined in `pyproject.toml`
- **Verbose mode**: Use `-v` flag to see full tracebacks on errors
- **Progress tracking**: CLI uses Rich progress bars during collection/sync
- **Error handling**: GitHubCLIError exception for gh command failures
- **Sync safety**: Dirty repos are never modified, always skipped
