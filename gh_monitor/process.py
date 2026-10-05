"""Subprocess helper shared by the git-driving components."""

import subprocess
from pathlib import Path


def run_command(args: list[str], cwd: Path | None = None) -> tuple[bool, str]:
    """Run a command and return (success, output), output falling back to stderr."""
    result = subprocess.run(  # noqa: S603 - args are built internally, never from a shell
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd,
        check=False,
    )
    output = result.stdout.strip() or result.stderr.strip()
    return result.returncode == 0, output
