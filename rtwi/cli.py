import json
import os
import signal
import subprocess
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from rtwi import __version__, daemon, rollmac, self_update
from rtwi import config as cfg
from rtwi.fix import run_fix
from rtwi.log import debug_enabled, setup_logging
from rtwi.machine import RTMachine
from rtwi.models import AuthState, is_within_schedule

app = typer.Typer(
    help=(
        "Auto-sign-in to the Rostelecom Wi-Fi captive portal "
        "([bold]auth.wifi.rt.ru[/bold]) with optional MAC roll to "
        "reset usage limits"
    ),
    no_args_is_help=True,
    invoke_without_command=True,
    rich_markup_mode="rich",
)
console = Console()

_TS_FMT = "%H:%M:%S"


def _ts() -> str:
    """Return current time (HH:MM:SS) for sequential log lines."""
    return time.strftime(_TS_FMT)


_EXIT_FOR_STATE = {
    AuthState.FAILED: 1,
    AuthState.WAIT_SMS: 2,
    AuthState.WAIT_CALL: 3,
    AuthState.FORBIDDEN: 4,
    AuthState.OFFLINE: 5,
    AuthState.DISABLED_BY_SCHEDULE: 6,
}


def _load_config() -> cfg.Config:
    try:
        return cfg.load_config()
    except cfg.ConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


def _make_machine() -> RTMachine:
    return RTMachine(_load_config())


def _maybe_sudo(command: list[str], sudo: bool) -> None:
    """Re-run the CLI as root when `sudo` was requested and not already root."""
    if sudo and not rollmac.is_root():
        console.print("[yellow]elevating to root...[/yellow]")
        raise typer.Exit(rollmac.self_elevate(command))


def _daemon_start(interval: int) -> None:
    """Start the watch loop as a detached background daemon."""
    daemon.start(interval=interval, pid_path=cfg.DAEMON_PID_PATH)


@app.callback()
def cli_main(
    _ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", is_eager=True, help="Show version and exit."
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging."),
) -> None:
    """Root CLI entry point; handles --version and --debug."""
    setup_logging(debug=debug or debug_enabled())
    if version:
        console.print(f"rtwi {__version__}")
        raise typer.Exit


@app.command()
def status(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show Wi-Fi state and the portal authorization status."""
    machine = _make_machine()
    try:
        wifi_state, portal = machine.status()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if as_json:
        console.print(
            json.dumps(
                {
                    "network": wifi_state.network,
                    "mac": wifi_state.mac,
                    "ip": wifi_state.ip,
                    "ping_ms": wifi_state.ping_ms,
                    "portal": portal.value,
                },
                indent=2,
            )
        )
        return
    table = Table(title="rtwi status")
    table.add_column("Tier")
    table.add_column("Value")
    table.add_row("Network", wifi_state.network)
    table.add_row("MAC", wifi_state.mac)
    table.add_row("IP", "—" if not wifi_state.ip else wifi_state.ip)
    table.add_row(
        "Ping",
        "—" if wifi_state.ping_ms is None else f"{wifi_state.ping_ms:.1f} ms",
    )
    table.add_row("Portal", _portal_label(portal))
    sched = machine.config.schedule
    if sched.enabled:
        days_str = ",".join(str(d) for d in sched.days)
        table.add_row(
            "Schedule",
            f"{sched.start.strftime('%H:%M')}-{sched.end.strftime('%H:%M')} "
            f"days=[{days_str}]",
        )
        within = is_within_schedule(sched)
        table.add_row(
            "Within schedule",
            "[green]yes[/green]" if within else "[red]no[/red]",
        )
    console.print(table)


def _portal_label(state: AuthState) -> str:
    labels = {
        AuthState.SUCCESS: "[green]authorized[/green]",
        AuthState.NEED_AUTH: "[yellow]need authorization[/yellow]",
        AuthState.WAIT_SMS: "[yellow]awaiting SMS code[/yellow]",
        AuthState.WAIT_CALL: "[yellow]awaiting call[/yellow]",
        AuthState.FORBIDDEN: "[red]forbidden (limit reached)[/red]",
        AuthState.DISABLED_BY_SCHEDULE: "[red]network disabled by schedule[/red]",
        AuthState.OFFLINE: "[yellow]offline[/yellow]",
        AuthState.FAILED: "[red]failed[/red]",
        AuthState.PROCESSING: "[yellow]processing[/yellow]",
    }
    return labels.get(state, state.value)


@app.command()
def fix(
    sudo: bool = typer.Option(
        False, "--sudo", help="elevate to root to allow MAC rolls"
    ),
) -> None:
    """Authorize on the portal, rolling the MAC when blocked by limits."""
    _maybe_sudo(["fix", "--sudo"], sudo)
    machine = _make_machine()
    result = run_fix(machine)
    state_label = _portal_label(result.state)
    console.print(f"state: {state_label}")
    console.print(result.message)
    if result.rolls:
        console.print(f"mac rolled: {result.rolls} time(s)")
    raise typer.Exit(_EXIT_FOR_STATE.get(result.state, 0))


@app.command("sms")
def sms_command(
    code: str = typer.Argument(help="SMS confirmation code from the portal"),
) -> None:
    """Submit an SMS confirmation code."""
    machine = _make_machine()
    result = machine.sms(code)
    console.print(_portal_label(result.state))
    console.print(result.message)
    raise typer.Exit(_EXIT_FOR_STATE.get(result.state, 0))


@app.command()
def roll(
    sudo: bool = typer.Option(
        False, "--sudo", help="elevate to root to change the MAC address"
    ),
) -> None:
    """Roll the Wi-Fi MAC address to reset network limits."""
    _maybe_sudo(["roll", "--sudo"], sudo)
    machine = _make_machine()
    try:
        mac = machine.roll()
    except rollmac.RollMACError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if mac is None:
        console.print("[yellow]MAC roll requires root: run 'rtwi roll --sudo'[/yellow]")
        raise typer.Exit(code=1)
    console.print(f"MAC rolled to [green]{mac}[/green]")


@app.command()
def config() -> None:
    """Open the config file in $EDITOR (default vim)."""
    path = cfg.CONFIG_PATH
    if not path.exists():
        cfg.load_config()
    editor = os.environ.get("EDITOR") or "vim"
    console.print(f"editing {path}")
    subprocess.run([editor, str(path)])  # noqa: S603


@app.command("self-update")
def self_update_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="skip the confirmation prompt"),
) -> None:
    """Update the rtwi binary to the latest release."""
    console.print("checking for updates...")
    result = self_update.check_for_update()
    if result.updated or result.current == result.latest:
        console.print(f"[green]{result.message}[/green]")
        raise typer.Exit

    console.print(f"[yellow]{result.message}[/yellow]")
    if not yes and not typer.confirm("Download and install the update?"):
        console.print("cancelled")
        raise typer.Exit(code=1)

    console.print("downloading...")
    result = self_update.perform_update()
    console.print(f"[green]{result.message}[/green]")
    console.print("restart your shell or run 'rtwi --version' to verify")


@app.command()
def watch(
    interval: int = typer.Option(
        60, "--interval", "-i", help="Check interval in seconds"
    ),
    sudo: bool = typer.Option(
        False, "--sudo", help="elevate to root to allow MAC rolls"
    ),
    as_daemon: bool = typer.Option(
        False, "--daemon", help="run in the background instead of the foreground"
    ),
) -> None:
    """Background daemon: monitor the portal and auto-authorize continuously."""
    if as_daemon:
        _maybe_sudo(["watch", "--sudo", "--daemon", "--interval", str(interval)], sudo)
        _daemon_start(interval)
        return
    _maybe_sudo(["watch", "--sudo", "--interval", str(interval)], sudo)
    machine = _make_machine()
    running = True

    def _handle_signal(signum: int, _frame: object) -> None:
        nonlocal running
        console.print(
            f"{_ts()} [yellow]received signal {signum}, shutting down...[/yellow]"
        )
        running = False

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    console.print(
        f"{_ts()} [green]watching portal every {interval}s (Ctrl-C to stop)[/green]"
    )

    while running:
        try:
            if not machine.connected():
                console.print(f"{_ts()} [yellow]offline, waiting...[/yellow]")
            else:
                result = run_fix(machine)
                if result.state == AuthState.SUCCESS:
                    console.print(
                        f"{_ts()} [green]authorized[/green]"
                        + (f" (mac rolled {result.rolls}x)" if result.rolls else "")
                    )
                elif result.state == AuthState.DISABLED_BY_SCHEDULE:
                    console.print(f"{_ts()} [red]network disabled by schedule[/red]")
                elif result.state == AuthState.WAIT_SMS:
                    console.print(
                        f"{_ts()} [yellow]"
                        "SMS code required: run `rtwi sms <code>`[/yellow]"
                    )
                elif result.state == AuthState.WAIT_CALL:
                    console.print(f"{_ts()} [yellow]{result.message}[/yellow]")
                elif result.state == AuthState.FORBIDDEN:
                    console.print(f"{_ts()} [red]forbidden, rolls exhausted[/red]")
                else:
                    console.print(f"{_ts()} [red]{result.message}[/red]")
        except KeyboardInterrupt:
            break
        except Exception as exc:
            console.print(f"{_ts()} [red]error: {exc}[/red]")

        try:
            end = time.monotonic() + interval
            while running and time.monotonic() < end:
                time.sleep(min(1.0, end - time.monotonic()))
        except KeyboardInterrupt:
            break

    console.print(f"{_ts()} [green]watch stopped[/green]")


@app.command()
def stop(
    yes: bool = typer.Option(False, "--yes", "-y", help="skip the confirmation prompt"),
) -> None:
    """Stop the running watch daemon."""
    if not yes and not typer.confirm("Stop the watch daemon?"):
        console.print("cancelled")
        raise typer.Exit(code=1)
    if daemon.stop(cfg.DAEMON_PID_PATH):
        console.print("[green]daemon stopped[/green]")
    else:
        console.print("[yellow]no daemon running[/yellow]")


@app.command()
def logs(
    follow: bool = typer.Option(
        True, "--follow/--no-follow", "-f/--follow", help="tail -f style output"
    ),
    tail: int = typer.Option(
        50, "--tail", "-n", min=0, help="lines shown before following"
    ),
) -> None:
    """Tail the daemon log; --no-follow prints the last N lines and exits."""
    if not cfg.LOG_PATH.exists():
        console.print(f"[yellow]no log yet: {cfg.LOG_PATH}[/yellow]")
        return
    if not follow:
        _print_log_tail(cfg.LOG_PATH, tail)
        return
    try:
        _follow_log(cfg.LOG_PATH, tail)
    except KeyboardInterrupt:
        console.print("\nstopped following logs")


def _print_log_tail(path: Path, lines: int) -> None:
    with path.open(errors="replace") as f:
        content = f.readlines()
    for line in content[-lines:]:
        console.print(line.rstrip())


def _follow_log(path: Path, tail: int) -> None:
    with path.open("rb") as f:
        pos = f.seek(0, os.SEEK_END)
    for line in _read_last_lines(path, tail):
        console.print(line)
    while True:
        with path.open("rb") as f:
            f.seek(pos)
            for raw in f:
                console.print(raw.decode(errors="replace").rstrip())
                pos = f.tell()
        time.sleep(1)


def _read_last_lines(path: Path, lines: int) -> list[str]:
    with path.open(errors="replace") as f:
        content = f.readlines()
    return [ln.rstrip() for ln in content[-lines:]]


if __name__ == "__main__":
    app()
