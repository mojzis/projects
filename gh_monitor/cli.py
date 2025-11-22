"""CLI interface for GitHub project monitor."""

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import Progress
from typing_extensions import Annotated

from .generators import generate_html_report, generate_markdown_report, generate_toon_report
from .models import MonitorReport
from .monitor import ProjectMonitor
from .syncer import GitSyncer

app = typer.Typer(
    help="Monitor GitHub project status and generate reports", no_args_is_help=True
)
console = Console()


@app.command()
def monitor(
    owner: Annotated[str, typer.Argument(help="GitHub organization or user")],
    output_dir: Annotated[
        Path, typer.Option("--output", "-o", help="Output directory for reports")
    ] = Path("reports"),
    days: Annotated[
        int,
        typer.Option(
            "--days", "-d", help="Monitor repos changed in last N days", min=1, max=365
        ),
    ] = 30,
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: toon, markdown, html, or all"),
    ] = "all",
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose output")
    ] = False,
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
        outputs = []

        if fmt in ["toon", "all"]:
            toon_path = output_dir / "report.toon"
            generate_toon_report(report, toon_path)
            outputs.append(("TOON", toon_path))

        if fmt in ["markdown", "md", "all"]:
            md_path = output_dir / "report.md"
            generate_markdown_report(report, md_path)
            outputs.append(("Markdown", md_path))

        if fmt in ["html", "all"]:
            html_path = output_dir / "report.html"
            generate_html_report(report, html_path)
            outputs.append(("HTML", html_path))

        # Display results
        console.print(
            f"\n[bold green]Successfully monitored {len(repositories)} repositories[/bold green]"
        )
        console.print(f"  • {report.total_open_prs} open PRs")
        console.print(f"  • {report.total_branches_without_prs} branches without PRs\n")

        console.print("[bold]Generated reports:[/bold]")
        for format_name, path in outputs:
            console.print(f"  [green]✓[/green] {format_name}: {path}")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}", err=True)
        if verbose:
            import traceback

            console.print(traceback.format_exc(), err=True)
        raise typer.Exit(1)


@app.command()
def version():
    """Show version information."""
    console.print("gh-project-monitor version 0.1.0")


@app.command()
def sync(
    owner: Annotated[str, typer.Argument(help="GitHub organization or user to sync")],
    git_dir: Annotated[
        Path, typer.Option("--dir", "-d", help="Local git directory")
    ] = Path("~/git"),
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose output")
    ] = False,
):
    """Sync GitHub repositories to local directory.

    Compares repositories from GitHub with local ~/git directory:
    - Missing repos are cloned
    - Existing clean repos are pulled
    - Dirty repos (uncommitted changes) are skipped
    """
    try:
        syncer = GitSyncer(owner, git_dir, verbose)

        console.print(
            f"[bold blue]Syncing repositories for {owner} to {syncer.git_dir}...[/bold blue]"
        )

        with Progress() as progress:
            task = progress.add_task("[cyan]Syncing...", total=100)
            report = syncer.sync_all(
                progress_callback=lambda p: progress.update(task, completed=p)
            )

        # Summary output
        console.print()

        if report.cloned:
            console.print(f"[bold green]Cloned ({len(report.cloned)}):[/bold green]")
            for name in report.cloned:
                console.print(f"  [green]+[/green] {name}")

        if report.pulled:
            console.print(f"[bold blue]Updated ({len(report.pulled)}):[/bold blue]")
            for name in report.pulled:
                console.print(f"  [blue]↓[/blue] {name}")

        if report.already_current:
            console.print(
                f"[dim]Already current ({len(report.already_current)})[/dim]"
            )

        if report.skipped_dirty:
            console.print(
                f"[bold yellow]Skipped - dirty ({len(report.skipped_dirty)}):[/bold yellow]"
            )
            for name in report.skipped_dirty:
                console.print(f"  [yellow]![/yellow] {name}")

        if report.skipped_error:
            console.print(
                f"[bold red]Errors ({len(report.skipped_error)}):[/bold red]"
            )
            for name in report.skipped_error:
                console.print(f"  [red]✗[/red] {name}")

        # Final summary line
        total = (
            len(report.cloned)
            + len(report.pulled)
            + len(report.already_current)
            + len(report.skipped_dirty)
            + len(report.skipped_error)
        )
        console.print(f"\n[bold]Total: {total} repositories[/bold]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}", err=True)
        if verbose:
            import traceback

            console.print(traceback.format_exc(), err=True)
        raise typer.Exit(1)


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
