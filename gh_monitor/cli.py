"""CLI interface for GitHub project monitor."""

import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Annotated

import click.exceptions
import typer
from rich.console import Console
from rich.progress import Progress

from .generators import (
    generate_html_report,
    generate_list_report,
    generate_markdown_report,
    generate_toon_report,
)
from .models import MonitorReport, SyncReport
from .monitor import ProjectMonitor
from .syncer import GitSyncer


def _print_sync_report(report: SyncReport) -> None:
    """Print sync report summary to console."""
    if report.cloned:
        console.print(f"[bold green]Cloned ({len(report.cloned)}):[/bold green]")
        for name in report.cloned:
            console.print(f"  [green]+[/green] {name}")

    if report.pulled:
        console.print(f"[bold blue]Updated ({len(report.pulled)}):[/bold blue]")
        for name in report.pulled:
            console.print(f"  [blue]↓[/blue] {name}")

    if report.already_current:
        console.print(f"[dim]Already current ({len(report.already_current)})[/dim]")

    if report.skipped_dirty:
        console.print(f"[bold yellow]Skipped - dirty ({len(report.skipped_dirty)}):[/bold yellow]")
        for name in report.skipped_dirty:
            console.print(f"  [yellow]![/yellow] {name}")

    if report.skipped_error:
        console.print(f"[bold red]Errors ({len(report.skipped_error)}):[/bold red]")
        for name in report.skipped_error:
            console.print(f"  [red]✗[/red] {name}")

    total = (
        len(report.cloned)
        + len(report.pulled)
        + len(report.already_current)
        + len(report.skipped_dirty)
        + len(report.skipped_error)
    )
    console.print(f"\n[bold]Total: {total} repositories[/bold]")


app = typer.Typer(
    help="Monitor GitHub project status and generate reports",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
console = Console()
error_console = Console(stderr=True)


def _generate_reports(
    report: MonitorReport, output_dir: Path, fmt: str
) -> tuple[list[tuple[str, Path]], list[tuple[str, Exception]]]:
    """Generate reports in requested formats, collecting successes and errors."""
    outputs: list[tuple[str, Path]] = []
    errors: list[tuple[str, Exception]] = []

    format_configs = [
        ("toon", ["toon", "all"], "report.toon", generate_toon_report),
        ("Markdown", ["markdown", "md", "all"], "report.md", generate_markdown_report),
        ("HTML", ["html", "all"], "report.html", generate_html_report),
        ("List", ["list", "all"], "list.txt", generate_list_report),
    ]

    for name, formats, filename, generator in format_configs:
        if fmt in formats:
            path = output_dir / filename
            try:
                generator(report, path)
                outputs.append((name, path))
            except Exception as e:
                errors.append((name, e))

    return outputs, errors


def _publish_to_gh_pages(html_path: Path, verbose: bool = False) -> None:
    """Publish HTML report to gh-pages branch.

    Args:
        html_path: Path to the HTML report file
        verbose: Enable verbose output

    Raises:
        RuntimeError: If git operations fail
    """

    def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip()}")
        return result

    # Get current branch to return to later
    result = run_git("rev-parse", "--abbrev-ref", "HEAD")
    original_branch = result.stdout.strip()

    # Get repository root
    result = run_git("rev-parse", "--show-toplevel")
    repo_root = Path(result.stdout.strip())

    # Check if gh-pages exists locally or remotely
    local_exists = run_git("rev-parse", "--verify", "gh-pages", check=False).returncode == 0
    remote_exists = (
        run_git("ls-remote", "--heads", "origin", "gh-pages", check=False).stdout.strip() != ""
    )

    try:
        if local_exists:
            run_git("checkout", "gh-pages")
        elif remote_exists:
            run_git("checkout", "-b", "gh-pages", "origin/gh-pages")
        else:
            # Create orphan branch
            run_git("checkout", "--orphan", "gh-pages")
            run_git("rm", "-rf", ".")
            run_git("clean", "-fd")

        # Copy HTML report as index.html
        dest_path = repo_root / "index.html"
        shutil.copy2(html_path, dest_path)

        # Check if there are changes to commit
        run_git("add", "index.html")
        status = run_git("status", "--porcelain")

        if status.stdout.strip():
            run_git("commit", "-m", f"Update report - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            run_git("push", "-u", "origin", "gh-pages")
        elif verbose:
            console.print("[dim]No changes to publish[/dim]")

    finally:
        # Always return to original branch
        run_git("checkout", original_branch, check=False)


def _display_and_publish_results(
    report: MonitorReport,
    outputs: list[tuple[str, Path]],
    errors: list[tuple[str, Exception]],
    output_dir: Path,
    publish: bool,
    verbose: bool,
) -> None:
    """Display report results and optionally publish to gh-pages."""
    # Display results
    console.print(
        f"\n[bold green]Successfully monitored {len(report.repositories)} repositories[/bold green]"
    )
    console.print(f"  • {report.total_open_prs} open PRs")
    console.print(f"  • {report.total_branches_without_prs} branches without PRs\n")

    if outputs:
        console.print("[bold]Generated reports:[/bold]")
        for format_name, path in outputs:
            console.print(f"  [green]✓[/green] {format_name}: {path}")

    if errors:
        error_console.print("\n[bold yellow]Warnings during report generation:[/bold yellow]")
        for format_name, err in errors:
            error_console.print(f"  [yellow]![/yellow] {format_name}: {err}")

    if not outputs and errors:
        error_console.print("[bold red]Error:[/bold red] No reports were generated")
        raise typer.Exit(1)

    # Publish to gh-pages if requested
    if publish:
        html_path = output_dir / "report.html"
        if html_path.exists():
            console.print("\n[bold blue]Publishing to gh-pages...[/bold blue]")
            try:
                _publish_to_gh_pages(html_path, verbose)
                console.print("[green]✓[/green] Published to gh-pages branch")
            except RuntimeError as e:
                error_console.print(f"[yellow]Warning:[/yellow] Failed to publish: {e}")
        else:
            error_console.print("[yellow]Warning:[/yellow] HTML report not found, skipping publish")


@app.command()
def monitor(
    owner: Annotated[str, typer.Argument(help="GitHub organization or user")],
    output_dir: Annotated[
        Path, typer.Option("--output", "-o", help="Output directory for reports")
    ] = Path("reports"),
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Monitor repos changed in last N days", min=1, max=365),
    ] = 30,
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: toon, markdown, html, list, or all"),
    ] = "all",
    publish: Annotated[
        bool,
        typer.Option("--publish/--no-publish", "-p", help="Publish HTML report to gh-pages branch"),
    ] = True,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output")] = False,
):
    """Monitor GitHub projects and generate reports."""
    try:
        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize monitor
        proj_monitor = ProjectMonitor(owner, days, verbose)

        # Collect data with progress indicator
        console.print(f"[bold blue]Monitoring repositories for {owner}...[/bold blue]")

        repositories = []
        with Progress() as progress:
            task = progress.add_task("[cyan]Collecting data...", total=100)
            repositories = proj_monitor.collect_all_data(
                progress_callback=lambda p: progress.update(task, completed=p)
            )

        if not repositories:
            console.print(
                f"[yellow]No repositories found with activity in the last {days} days[/yellow]"
            )
            raise typer.Exit(0)

        # Generate report
        report = MonitorReport(
            generated_at=datetime.now(),
            scan_period_days=days,
            repositories=repositories,
        )

        # Output based on format
        outputs, errors = _generate_reports(report, output_dir, fmt)

        # Display results and optionally publish
        _display_and_publish_results(report, outputs, errors, output_dir, publish, verbose)

    except (SystemExit, click.exceptions.Exit):
        # Re-raise exit exceptions without modification
        raise
    except Exception as e:
        error_console.print(f"[bold red]Error:[/bold red] {e}")
        if verbose:
            import traceback

            error_console.print(traceback.format_exc())
        raise typer.Exit(1) from None


@app.command()
def version():
    """Show version information."""
    console.print("gh-project-monitor version 0.1.0")


@app.command()
def sync(
    owner: Annotated[str, typer.Argument(help="GitHub organization or user to sync")],
    git_dir: Annotated[Path, typer.Option("--dir", help="Local git directory")] = Path("~/git"),
    days: Annotated[
        int,
        typer.Option(
            "--days", "-d", help="Only sync repos modified in last N days", min=1, max=365
        ),
    ] = 45,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output")] = False,
):
    """Sync GitHub repositories to local directory.

    Compares repositories from GitHub with local ~/git directory:
    - Missing repos are cloned
    - Existing clean repos are pulled
    - Dirty repos (uncommitted changes) are skipped

    Use --days to limit syncing to recently active repositories.
    """
    try:
        syncer = GitSyncer(owner, git_dir, verbose, days)

        msg = (
            f"Syncing repositories for {owner} (active in last {days} days) to {syncer.git_dir}..."
        )
        console.print(f"[bold blue]{msg}[/bold blue]")

        with Progress() as progress:
            task = progress.add_task("[cyan]Syncing...", total=100)
            report = syncer.sync_all(progress_callback=lambda p: progress.update(task, completed=p))

        console.print()
        _print_sync_report(report)

    except (SystemExit, click.exceptions.Exit):
        raise
    except Exception as e:
        error_console.print(f"[bold red]Error:[/bold red] {e}")
        if verbose:
            import traceback

            error_console.print(traceback.format_exc())
        raise typer.Exit(1) from None


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
