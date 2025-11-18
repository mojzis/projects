# GitHub Project Monitor Tool - Implementation Plan (Updated)

## Executive Summary

This document outlines the architecture and implementation approach for a Python CLI tool that monitors GitHub project status using the GitHub CLI (gh). The tool collects comprehensive project health metrics and outputs reports in **TOON** (Token-Oriented Object Notation), **Markdown**, and **HTML** formats. Built with modern Python tooling (uv + typer), this tool provides a fast, type-safe, and maintainable solution for tracking GitHub repository activity.

**Key Updates from Original Plan:**
- Using **TOON format** instead of TOML for structured data output (30-60% more token-efficient for LLM consumption)
- Adding **Markdown report** with embedded structured data for human readability
- Keeping **HTML** for clean web-based visualization

## Technology Stack

**Core Technologies:**
- **Python 3.11+** (for modern type hints and standard library features)
- **GitHub CLI (gh)** via subprocess for repository queries
- **uv** (10-100x faster than pip/poetry, all-in-one package manager)
- **typer** (type-safe CLI framework leveraging Python type hints)

**Dependencies:**
- **toon_format** (official TOON encoder/decoder for Python)
- **Jinja2** (industry-standard HTML templating)
- **rich** (beautiful terminal output and progress indicators)

**Development Tools:**
- **pytest** (testing)
- **ty** (type checking by Astral, creators of ruff)
- **ruff** (ultra-fast linting and formatting)

## What is TOON?

TOON (Token-Oriented Object Notation) is a compact data format designed for LLM contexts with 30-60% token reduction versus JSON.

**Example:**

JSON:
```json
{
  "users": [
    {"id": 1, "name": "Alice", "role": "admin"},
    {"id": 2, "name": "Bob", "role": "user"}
  ]
}
```

TOON:
```
users[2]{id,name,role}:
1,Alice,admin
2,Bob,user
```

**Package:** `toon_format` on PyPI (official Python implementation).

## Project Architecture

### High-Level Design

The tool follows a clean separation of concerns with three primary layers:

1. **Data Collection Layer**: Interacts with GitHub CLI to gather repository metrics
2. **Business Logic Layer**: Processes and structures collected data
3. **Output Layer**: Generates TOON, Markdown, and HTML reports

**Data Flow:**
```
GitHub CLI (subprocess) → Data Models (dataclasses) → Report Generators (TOON/MD/HTML) → Output Files
```

### Core Components

**GitHubCollector**: Responsible for executing gh CLI commands and parsing JSON responses. Handles rate limiting, error recovery, and pagination.

**ProjectMonitor**: Orchestrates data collection across multiple repositories. Filters repositories by date (last 30 days), coordinates data collection, and aggregates results.

**DataModels**: Type-safe dataclasses representing projects, commits, pull requests, branches, and CI runs. Provides serialization methods for all output formats.

**ReportGenerators**:
- `ToonGenerator`: Converts data models to TOON format using `toon_format.encode()`
- `MarkdownGenerator`: Creates human-readable Markdown reports with embedded structured data
- `HtmlGenerator`: Creates clean HTML reports using Jinja2 templates

**CLI Interface**: Typer-based command-line interface with intuitive commands, progress indicators via rich, and proper exit codes.

## Project Structure

```
gh-project-monitor/
├── src/
│   └── gh_monitor/
│       ├── __init__.py
│       ├── __main__.py              # Entry point for python -m gh_monitor
│       ├── cli.py                   # Typer CLI application
│       ├── collector.py             # GitHub CLI interaction
│       ├── monitor.py               # Main orchestration logic
│       ├── models.py                # Data models (dataclasses)
│       ├── generators/
│       │   ├── __init__.py
│       │   ├── toon_gen.py          # TOON output generation
│       │   ├── markdown_gen.py      # Markdown output generation
│       │   └── html_gen.py          # HTML output generation
│       ├── templates/
│       │   ├── report.html          # Jinja2 HTML template
│       │   └── report.md            # Jinja2 Markdown template
│       └── py.typed                 # PEP 561 marker
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_cli.py
│   ├── test_collector.py
│   ├── test_generators.py
│   └── test_models.py
├── .github/
│   └── workflows/
│       └── ci.yml                   # GitHub Actions CI
├── pyproject.toml
├── uv.lock
├── README.md
└── .python-version                  # Pin Python version
```

## Data Models

Type-safe dataclasses ensure consistency and enable IDE support:

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum

class CIStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    NO_CI = "no_ci"
    UNKNOWN = "unknown"

@dataclass
class Commit:
    sha: str
    message: str
    author: str
    date: datetime
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'sha': self.sha,
            'message': self.message,
            'author': self.author,
            'date': self.date.isoformat()
        }

@dataclass
class PullRequest:
    number: int
    title: str
    created_at: datetime
    author: str
    age_days: int
    url: str
    
    def to_dict(self) -> dict:
        return {
            'number': self.number,
            'title': self.title,
            'created_at': self.created_at.isoformat(),
            'author': self.author,
            'age_days': self.age_days,
            'url': self.url
        }

@dataclass
class CIRun:
    name: str
    status: str
    conclusion: Optional[str]
    created_at: datetime
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'status': self.status,
            'conclusion': self.conclusion,
            'created_at': self.created_at.isoformat()
        }

@dataclass
class Repository:
    name: str
    owner: str
    full_name: str
    url: str
    last_commit: Optional[Commit]
    open_prs: list[PullRequest]
    branches_without_prs: list[str]
    github_pages_enabled: bool
    github_pages_url: Optional[str]
    ci_status: CIStatus
    ci_recent_runs: list[CIRun]
    ci_success_rate: float
    last_updated: datetime
    
    # Additional metrics
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    primary_language: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'owner': self.owner,
            'full_name': self.full_name,
            'url': self.url,
            'last_commit': self.last_commit.to_dict() if self.last_commit else None,
            'open_prs': [pr.to_dict() for pr in self.open_prs],
            'pr_count': len(self.open_prs),
            'branches_without_prs': self.branches_without_prs,
            'branch_without_pr_count': len(self.branches_without_prs),
            'github_pages': {
                'enabled': self.github_pages_enabled,
                'url': self.github_pages_url
            },
            'ci': {
                'status': self.ci_status.value,
                'recent_runs': [run.to_dict() for run in self.ci_recent_runs],
                'success_rate': self.ci_success_rate
            },
            'last_updated': self.last_updated.isoformat(),
            'stats': {
                'stars': self.stars,
                'forks': self.forks,
                'open_issues': self.open_issues,
                'language': self.primary_language
            }
        }

@dataclass
class MonitorReport:
    generated_at: datetime
    scan_period_days: int
    repositories: list[Repository]
    total_repositories: int = field(init=False)
    total_open_prs: int = field(init=False)
    total_branches_without_prs: int = field(init=False)
    
    def __post_init__(self):
        self.total_repositories = len(self.repositories)
        self.total_open_prs = sum(len(r.open_prs) for r in self.repositories)
        self.total_branches_without_prs = sum(len(r.branches_without_prs) for r in self.repositories)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for TOON/JSON output."""
        return {
            'report_metadata': {
                'generated_at': self.generated_at.isoformat(),
                'scan_period_days': self.scan_period_days,
                'total_repositories': self.total_repositories,
                'total_open_prs': self.total_open_prs,
                'total_branches_without_prs': self.total_branches_without_prs
            },
            'repositories': [repo.to_dict() for repo in self.repositories]
        }
```

## Output Formats

### 1. TOON Format

Using the `toon_format` package to generate compact, LLM-friendly output:

```python
from toon_format import encode
from pathlib import Path

def generate_toon_report(report: MonitorReport, output_path: Path) -> None:
    """Generate TOON format report from MonitorReport."""
    data = report.to_dict()
    
    # Encode to TOON format
    toon_str = encode(data)
    
    # Write to file
    output_path.write_text(toon_str, encoding='utf-8')
```

**Expected TOON structure** (example with 2 repositories):

```
report_metadata{generated_at,scan_period_days,total_repositories,total_open_prs,total_branches_without_prs}:
  2025-11-17T10:30:00Z,30,2,8,5

repositories[2]{name,owner,full_name,url,pr_count,branch_without_pr_count,ci,stats}:
  awesome-project,myorg,myorg/awesome-project,https://github.com/myorg/awesome-project,5,3,success:0.95,100:45:12:Python
  another-repo,myorg,myorg/another-repo,https://github.com/myorg/another-repo,3,2,failure:0.60,45:20:8:JavaScript

repositories[0].last_commit{sha,message,author,date}:
  abc123def456,Fix critical bug in parser,Jane Doe,2025-11-15T14:20:00Z

repositories[0].open_prs[5]{number,title,author,age_days,url}:
  123,Add new feature,jdoe,7,https://github.com/myorg/awesome-project/pull/123
  124,Fix typo,asmith,5,https://github.com/myorg/awesome-project/pull/124
  125,Update deps,bjones,3,https://github.com/myorg/awesome-project/pull/125
  126,Refactor utils,clee,2,https://github.com/myorg/awesome-project/pull/126
  127,Add tests,dchen,1,https://github.com/myorg/awesome-project/pull/127

repositories[0].branches_without_prs[3]:
  feature/experimental
  hotfix/bug-123
  dev/prototype
```

### 2. Markdown Format

Human-readable report with embedded structured data:

**Template (templates/report.md):**

```markdown
# GitHub Project Monitor Report

**Generated:** {{ timestamp }}  
**Scan Period:** Last {{ scan_days }} days  
**Total Repositories:** {{ total_repos }}  
**Total Open PRs:** {{ total_prs }}  
**Total Branches Without PRs:** {{ total_branches }}

---

## Summary Statistics

| Metric | Count |
|--------|-------|
| Repositories Scanned | {{ total_repos }} |
| Total Open Pull Requests | {{ total_prs }} |
| Branches Without PRs | {{ total_branches }} |
| Repos with CI Passing | {{ passing_ci }} |
| Repos with CI Failing | {{ failing_ci }} |
| Repos with GitHub Pages | {{ pages_enabled }} |

---

{% for repo in repositories %}
## {{ repo.owner }}/{{ repo.name }}

**Repository:** [{{ repo.full_name }}]({{ repo.url }})  
**Language:** {{ repo.language or 'N/A' }} | **Stars:** ⭐ {{ repo.stars }} | **Forks:** 🔱 {{ repo.forks }} | **Issues:** {{ repo.open_issues }}

### 📝 Last Commit on Main

{% if repo.last_commit %}
- **SHA:** `{{ repo.last_commit.sha[:8] }}`
- **Message:** {{ repo.last_commit.message }}
- **Author:** {{ repo.last_commit.author }}
- **Date:** {{ repo.last_commit.date }}
{% else %}
No commit information available
{% endif %}

### 🔀 Open Pull Requests ({{ repo.open_prs|length }})

{% if repo.open_prs %}
| # | Title | Author | Age |
|---|-------|--------|-----|
{% for pr in repo.open_prs %}
| [#{{ pr.number }}]({{ pr.url }}) | {{ pr.title }} | @{{ pr.author }} | {{ pr.age_days }}d |
{% endfor %}
{% else %}
No open pull requests
{% endif %}

### 🌿 Branches Without PRs ({{ repo.branches_without_prs|length }})

{% if repo.branches_without_prs %}
{% for branch in repo.branches_without_prs %}
- `{{ branch }}`
{% endfor %}
{% else %}
All branches have associated PRs
{% endif %}

### 📄 GitHub Pages

{% if repo.github_pages_enabled %}
✅ **Enabled** - [Visit Site]({{ repo.github_pages_url }})
{% else %}
❌ Disabled
{% endif %}

### 🔧 CI/CD Pipeline

**Status:** {% if repo.ci_status == 'success' %}✅{% elif repo.ci_status == 'failure' %}❌{% elif repo.ci_status == 'pending' %}⏳{% else %}❓{% endif %} {{ repo.ci_status|upper }}  
**Success Rate:** {{ (repo.ci_success_rate * 100)|round(1) }}%

{% if repo.ci_recent_runs %}
**Recent Runs:**
{% for run in repo.ci_recent_runs[:5] %}
- {{ run.name }}: {{ run.status }} ({{ run.conclusion or 'in progress' }})
{% endfor %}
{% endif %}

---

{% endfor %}

## 📊 Repository Overview

```
{% for repo in repositories %}
{{ repo.name }}: {{ repo.pr_count }} PRs | {{ repo.branch_without_pr_count }} orphaned branches | CI {{ repo.ci_status }}
{% endfor %}
```

---

*Generated by GitHub Project Monitor*
```

**Python generator code:**

```python
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

def generate_markdown_report(report: MonitorReport, output_path: Path) -> None:
    """Generate Markdown report using Jinja2 template."""
    template_dir = Path(__file__).parent.parent / 'templates'
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template('report.md')
    
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
        repositories=[{
            'name': r.name,
            'owner': r.owner,
            'full_name': r.full_name,
            'url': r.url,
            'language': r.primary_language,
            'stars': r.stars,
            'forks': r.forks,
            'open_issues': r.open_issues,
            'last_commit': r.last_commit,
            'open_prs': r.open_prs,
            'branches_without_prs': r.branches_without_prs,
            'github_pages_enabled': r.github_pages_enabled,
            'github_pages_url': r.github_pages_url,
            'ci_status': r.ci_status.value,
            'ci_success_rate': r.ci_success_rate,
            'ci_recent_runs': r.ci_recent_runs,
            'pr_count': len(r.open_prs),
            'branch_without_pr_count': len(r.branches_without_prs)
        } for r in report.repositories]
    )
    
    output_path.write_text(markdown, encoding='utf-8')
```

### 3. HTML Format

Clean, mostly white page with modern styling (same as in original plan, see detailed HTML template in original plan document).

**Key CSS principles for "mostly white" design:**
- Background: `#f8f9fa` (very light gray)
- Cards: `white` with subtle shadows
- Accent: `#3498db` (soft blue) for headers
- Minimal colors, maximum whitespace
- Clean typography with system fonts

## GitHub CLI Integration

### Key gh CLI Commands

**List repositories with recent activity:**
```bash
gh repo list OWNER --json name,pushedAt,updatedAt,stargazerCount,forkCount,url --limit 1000
```

Then filter in Python by `pushedAt` date to get repos changed in last 30 days.

**Last commit on main branch:**
```bash
gh api repos/OWNER/REPO/commits/main
```

**Open pull requests:**
```bash
gh pr list --repo OWNER/REPO --state open \
  --json number,title,createdAt,author,url --limit 100
```

**All branches:**
```bash
gh api repos/OWNER/REPO/branches --paginate
```

**Branches with PRs (to find orphaned branches):**
```bash
gh pr list --repo OWNER/REPO --state all \
  --json headRefName --limit 1000
```

**GitHub Pages status:**
```bash
gh api repos/OWNER/REPO/pages
# Returns 404 if not enabled, otherwise returns status and URL
```

**CI/CD pipeline status:**
```bash
gh run list --repo OWNER/REPO --limit 20 \
  --json status,conclusion,name,createdAt
```

**Repository details (stars, forks, language, issues):**
```bash
gh repo view OWNER/REPO --json stargazerCount,forkCount,openIssues,primaryLanguage
```

### Python wrapper example:

```python
import subprocess
import json
from typing import Any

def run_gh_command(args: list[str]) -> dict[str, Any] | list[Any]:
    """Execute gh CLI command with error handling."""
    result = subprocess.run(
        ['gh'] + args,
        capture_output=True,
        text=True,
        encoding='utf-8',
        check=False
    )
    
    if result.returncode != 0:
        raise GitHubCLIError(f"gh command failed: {result.stderr}")
    
    return json.loads(result.stdout) if result.stdout else {}

def get_repositories(owner: str, since_days: int = 30) -> list[dict]:
    """Get repositories modified in the last N days."""
    from datetime import datetime, timedelta, timezone
    
    # Get all repos
    repos = run_gh_command([
        'repo', 'list', owner,
        '--json', 'name,pushedAt,updatedAt,stargazerCount,forkCount,url',
        '--limit', '1000'
    ])
    
    # Filter by date
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    
    filtered = []
    for repo in repos:
        pushed_at = datetime.fromisoformat(repo['pushedAt'].replace('Z', '+00:00'))
        if pushed_at > cutoff:
            filtered.append(repo)
    
    return filtered
```

## CLI Interface with Typer

```python
import typer
from typing_extensions import Annotated
from pathlib import Path
from rich.console import Console
from rich.progress import Progress

app = typer.Typer(
    help="Monitor GitHub project status and generate reports",
    no_args_is_help=True
)
console = Console()

@app.command()
def monitor(
    owner: Annotated[str, typer.Argument(help="GitHub organization or user")],
    output_dir: Annotated[Path, typer.Option(
        "--output", "-o",
        help="Output directory for reports"
    )] = Path("reports"),
    days: Annotated[int, typer.Option(
        "--days", "-d",
        help="Monitor repos changed in last N days",
        min=1, max=365
    )] = 30,
    format: Annotated[str, typer.Option(
        "--format", "-f",
        help="Output format: toon, markdown, html, or all"
    )] = "all",
    verbose: Annotated[bool, typer.Option(
        "--verbose", "-v",
        help="Enable verbose output"
    )] = False
):
    """Monitor GitHub projects and generate reports."""
    
    try:
        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize monitor
        monitor = ProjectMonitor(owner, days, verbose)
        
        # Collect data with progress indicator
        console.print(f"[bold blue]Monitoring repositories for {owner}...[/bold blue]")
        
        with Progress() as progress:
            task = progress.add_task("[cyan]Collecting data...", total=100)
            repositories = monitor.collect_all_data(
                progress_callback=lambda p: progress.update(task, completed=p)
            )
        
        # Generate report
        report = MonitorReport(
            generated_at=datetime.now(),
            scan_period_days=days,
            repositories=repositories
        )
        
        # Output based on format
        outputs = []
        
        if format in ["toon", "all"]:
            toon_path = output_dir / "report.toon"
            generate_toon_report(report, toon_path)
            outputs.append(("TOON", toon_path))
        
        if format in ["markdown", "md", "all"]:
            md_path = output_dir / "report.md"
            generate_markdown_report(report, md_path)
            outputs.append(("Markdown", md_path))
        
        if format in ["html", "all"]:
            html_path = output_dir / "report.html"
            generate_html_report(report, html_path)
            outputs.append(("HTML", html_path))
        
        # Display results
        console.print(f"\n[bold green]✓ Successfully monitored {len(repositories)} repositories[/bold green]")
        console.print(f"  • {report.total_open_prs} open PRs")
        console.print(f"  • {report.total_branches_without_prs} branches without PRs\n")
        
        console.print("[bold]Generated reports:[/bold]")
        for format_name, path in outputs:
            console.print(f"  [green]✓[/green] {format_name}: {path}")
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}", err=True)
        raise typer.Exit(1)

@app.command()
def version():
    """Show version information."""
    console.print("gh-project-monitor version 0.1.0")

def main():
    app()

if __name__ == "__main__":
    main()
```

## Package Configuration (pyproject.toml)

```toml
[project]
name = "gh-project-monitor"
version = "0.1.0"
description = "Monitor GitHub project status using gh CLI with TOON, Markdown, and HTML output"
readme = "README.md"
requires-python = ">=3.11"
authors = [
    {name = "Your Name", email = "you@example.com"}
]
dependencies = [
    "typer>=0.12.0",
    "toon-format>=0.1.0",  # TOON encoder/decoder
    "jinja2>=3.1.0",
    "rich>=13.7.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=4.1.0",
    "ty>=0.1.0",
    "ruff>=0.3.0",
]

[project.scripts]
gh-monitor = "gh_monitor.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ty]
python_version = "3.11"
strict = true

[tool.ruff]
line-length = 100
target-version = "py311"
select = ["E", "F", "B", "I", "N", "UP", "ANN", "S", "C90"]
ignore = ["ANN101", "ANN102"]

[tool.ruff.per-file-ignores]
"tests/*" = ["S101"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "--cov=gh_monitor --cov-report=html --cov-report=term"
```

## Setup and Installation

```bash
# Initialize project with uv
uv init --package gh-project-monitor
cd gh-project-monitor

# Add dependencies
uv add typer toon-format jinja2 rich

# Add dev dependencies
uv add --dev pytest pytest-cov ty ruff

# Install in development mode
uv sync

# Generate all formats
uv run gh-monitor myorg --days 30 --output reports/

# Generate specific format
uv run gh-monitor myorg --format toon --output reports/
uv run gh-monitor myorg --format markdown --output reports/
uv run gh-monitor myorg --format html --output reports/

# Or install globally
uv build
uv pip install dist/gh_project_monitor-0.1.0-py3-none-any.whl

# Then run directly
gh-monitor myorg --days 7
```

## Additional Metrics to Collect

Beyond the required metrics, the tool collects:

1. **Repository Statistics**
   - Star count
   - Fork count
   - Open issues count
   - Primary programming language

2. **Recent CI Runs**
   - Not just status, but list of recent runs
   - Workflow names
   - Success/failure patterns

3. **PR Age Analysis**
   - Calculate age in days for each PR
   - Identify stale PRs (>30 days old)

4. **Branch Information**
   - Total branch count
   - Active vs stale branches (based on last commit date)

## Testing Strategy

```python
# tests/test_generators.py
import pytest
from gh_monitor.models import Repository, MonitorReport, CIStatus
from gh_monitor.generators.toon_gen import generate_toon_report
from gh_monitor.generators.markdown_gen import generate_markdown_report
from toon_format import decode

def test_toon_generation(tmp_path):
    """Test TOON report generation and validate it can be decoded."""
    report = MonitorReport(
        generated_at=datetime.now(),
        scan_period_days=30,
        repositories=[
            Repository(
                name="test-repo",
                owner="test-owner",
                full_name="test-owner/test-repo",
                url="https://github.com/test-owner/test-repo",
                last_commit=None,
                open_prs=[],
                branches_without_prs=[],
                github_pages_enabled=False,
                github_pages_url=None,
                ci_status=CIStatus.SUCCESS,
                ci_recent_runs=[],
                ci_success_rate=1.0,
                last_updated=datetime.now()
            )
        ]
    )
    
    output_file = tmp_path / "test_report.toon"
    generate_toon_report(report, output_file)
    
    assert output_file.exists()
    
    # Validate TOON can be decoded
    toon_content = output_file.read_text()
    decoded = decode(toon_content)
    assert 'report_metadata' in decoded
    assert decoded['report_metadata']['total_repositories'] == 1

def test_markdown_generation(tmp_path):
    """Test Markdown report generation."""
    # Similar test for markdown generation
    pass
```

## CI/CD Integration

The tool is perfect for automated monitoring in GitHub Actions:

```yaml
name: Weekly Project Monitor

on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly on Sunday
  workflow_dispatch:

jobs:
  monitor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      
      - name: Install gh-monitor
        run: |
          cd gh-project-monitor
          uv sync
      
      - name: Run monitor
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          uv run gh-monitor ${{ github.repository_owner }} \
            --days 7 \
            --format all \
            --output reports/
      
      - name: Upload TOON report for LLM processing
        uses: actions/upload-artifact@v4
        with:
          name: toon-report
          path: reports/report.toon
      
      - name: Upload Markdown report
        uses: actions/upload-artifact@v4
        with:
          name: markdown-report
          path: reports/report.md
      
      - name: Upload HTML report
        uses: actions/upload-artifact@v4
        with:
          name: html-report
          path: reports/report.html
      
      # Optional: Send TOON report to LLM for analysis
      - name: Analyze with LLM (optional)
        run: |
          curl -X POST https://api.your-llm-service.com/analyze \
            -H "Content-Type: text/plain" \
            --data-binary @reports/report.toon
```

## Summary

This implementation plan provides a comprehensive solution for GitHub project monitoring with three output formats:

1. **TOON**: Token-efficient, LLM-optimized structured data
2. **Markdown**: Human-readable reports with embedded data
3. **HTML**: Beautiful web-based visualization

**Next Steps:**

1. Initialize project with uv and install dependencies
2. Implement data models with full type annotations
3. Build GitHub collector with gh CLI wrappers
4. Create TOON generator using `toon_format`
5. Create Markdown generator with Jinja2 template
6. Create HTML generator with clean CSS
7. Build Typer CLI with rich progress indicators
8. Write comprehensive tests
9. Set up CI/CD for automated monitoring
10. Document usage with examples
