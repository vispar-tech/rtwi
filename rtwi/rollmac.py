from __future__ import annotations

import os
import secrets
import shlex
import subprocess
import sys
import time

from rtwi import wifi
from rtwi.log import get_logger

logger = get_logger(__name__)

_AIRPORT = "/System/Library/PrivateFrameworks/Apple80211.framework/Resources/airport"


class RollMACError(RuntimeError):
    """Raised when a MAC change or roll step fails."""


def random_mac() -> str:
    """Generate a random locally-administered unicast MAC (02:xx:xx:xx:xx:xx)."""
    return "02:" + ":".join(f"{b:02x}" for b in secrets.token_bytes(5))


def change_mac(interface: str, mac: str) -> None:
    """Apply `mac` to the interface; raises RollMACError on any failed step."""
    if not wifi.toggle_wifi(interface, turn_on=True):
        raise RollMACError("could not power the Wi-Fi radio on")
    try:
        subprocess.check_call(  # noqa: S603
            [_AIRPORT, "-z"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        subprocess.check_call(  # noqa: S603
            ["ifconfig", interface, "ether", mac.lower()],  # noqa: S607
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        subprocess.check_call(
            ["networksetup", "-detectnewhardware"],  # noqa: S607
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except subprocess.CalledProcessError as exc:
        raise RollMACError(f"MAC change failed: {exc}") from exc


def roll_mac(interface: str, reconnect_timeout: int = 30) -> str | None:
    """Full roll: off -> change MAC -> on -> wait; returns the new MAC."""
    if not wifi.toggle_wifi(interface, turn_on=False):
        raise RollMACError("could not power the Wi-Fi radio off")
    time.sleep(2)
    mac = random_mac()
    while mac == wifi.current_mac(interface).lower():
        mac = random_mac()
    change_mac(interface, mac)
    time.sleep(2)
    if not wifi.toggle_wifi(interface, turn_on=True):
        raise RollMACError("could not power the Wi-Fi radio back on")
    if not wifi.wait_connected(interface, timeout=reconnect_timeout):
        raise RollMACError("Wi-Fi did not reconnect after the MAC roll")
    logger.info("rolled MAC to %s", mac)
    return mac


def is_root() -> bool:
    """Return True when the current process runs with euid 0."""
    return os.geteuid() == 0


def _binary_command() -> list[str]:
    """Command that re-enters the current program in a new process."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "rtwi"]


def self_elevate(extra_args: list[str], gui_prompt: bool = False) -> int:
    """Re-run the program as root via `sudo` (or an admin osascript dialog).

    Returns the exit code of the elevated invocation.
    """
    command = [*_binary_command(), *extra_args]
    if gui_prompt:
        script = 'do shell script "{}" with administrator privileges'.format(
            shlex.quote(" ".join(shlex.quote(a) for a in command))
        )
        proc = subprocess.run(  # noqa: S603
            ["osascript", "-e", script],  # noqa: S607
            check=False,
        )
        return proc.returncode
    proc = subprocess.run(  # noqa: S603
        ["sudo", "--", *command],  # noqa: S607
        check=False,
    )
    return proc.returncode
