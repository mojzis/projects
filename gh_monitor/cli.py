"""CLI interface for GitHub project monitor."""

from datetime import datetime
from pathlib import Path
from typing import Annotated

import click.exceptions
import typer
from rich.console import Console
from rich.progress import Progress

from .generators import generate_html_report, generate_markdown_report, generate_toon_report
from .models import MonitorReport
from .monitor import ProjectMonitor

app = typer.Typer(help="Monitor GitHub project status and generate reports", no_args_is_help=True)
console = Console()
error_console = Console(stderr=True)


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
        typer.Option("--format", "-f", help="Output format: toon, markdown, html, or all"),
    ] = "all",
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

    except (SystemExit, click.exceptions.Exit):
        # Re-raise exit exceptions without modification
        raise
    except Exception as e:
        error_console.print(f"[bold red]Error:[/bold red] {e}")
        if verbose:
            import traceback

            error_console.print(traceback.format_exc())
        raise typer.Exit(1)


@app.command()
def version():
    """Show version information."""
    console.print("gh-project-monitor version 0.1.0")


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
