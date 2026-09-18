"""Launch background workers with independent standard streams."""

import subprocess
from pathlib import Path


def start_background(command: list[str], working_directory: Path, log_directory: Path) -> int:
    log_directory.mkdir(parents=True, exist_ok=True)
    # Independent streams and restricted handle inheritance let the launcher
    # exit without keeping its own command session attached to the worker.
    with (
        (log_directory / "stdout.log").open("ab") as stdout,
        (log_directory / "stderr.log").open("ab") as stderr,
    ):
        process = subprocess.Popen(
            command,
            cwd=working_directory,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    return process.pid
