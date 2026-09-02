"""Background daemon lifecycle: re-run the ``watch`` loop detached.

Mirrors the openrot daemon: fork a detached background process, route its
output to the log file, remember the pid, and terminate it on demand.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

from rich.console import Console

from rtwi import config as cfg

console = Console()


def is_running(pid: int) -> bool:
    """Return True when a process with the given pid is alive."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def save_pid(pid: int, path: Path = cfg.DAEMON_PID_PATH) -> None:
    """Write the daemon pid to `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(pid))
    path.chmod(0o600)


def load_pid(path: Path = cfg.DAEMON_PID_PATH) -> int | None:
    """Read the daemon pid from `path`, or None when absent or invalid."""
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except ValueError:
        return None


def _command(interval: int) -> list[str]:
    """Command that re-runs ``watch`` as a detached foreground process."""
    args = ["watch", "--interval", str(interval)]
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, "-m", "rtwi", *args]


def start(*, interval: int, pid_path: Path = cfg.DAEMON_PID_PATH) -> None:
    """Fork the ``watch`` loop into a background daemon process.

    Refuses to start while the recorded pid is still alive; otherwise writes
    the fresh pid to ``pid_path`` and routes the daemon's output to the log.
    """
    existing = load_pid(pid_path)
    if existing is not None:
        if is_running(existing):
            console.print("[yellow]daemon already running[/yellow]")
            return
        pid_path.unlink(missing_ok=True)
    with cfg.LOG_PATH.open("ab") as log_f:
        proc = subprocess.Popen(  # noqa: S603
            _command(interval),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    save_pid(proc.pid, path=pid_path)
    console.print(f"daemon started (pid {proc.pid}), log: {cfg.LOG_PATH}")


def stop(pid_path: Path = cfg.DAEMON_PID_PATH) -> bool:
    """Terminate the watch daemon and remove its pid file."""
    pid = load_pid(pid_path)
    if pid is None or not is_running(pid):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    pid_path.unlink(missing_ok=True)
    return True
