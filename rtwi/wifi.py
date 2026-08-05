from __future__ import annotations

import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

from rtwi.log import get_logger
from rtwi.models import Config, WiFiState

logger = get_logger(__name__)

_NOT_CONNECTED = "Не подключено"


def _run(args: list[str], timeout: float = 5) -> subprocess.CompletedProcess[str]:
    """Run a host command, capturing output (safe: no shell)."""
    return subprocess.run(  # noqa: S603
        args, capture_output=True, text=True, timeout=timeout
    )


def _check(args: list[str], timeout: float = 5) -> None:
    """Run a host command failing loudly on a non-zero exit code."""
    subprocess.check_call(  # noqa: S603
        args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout
    )


def list_interfaces() -> dict[str, str]:
    """Map hardware port names to device names via networksetup."""
    result = _run(["networksetup", "-listallhardwareports"])
    if result.returncode != 0:
        logger.warning("networksetup -listallhardwareports failed: %s", result.stderr)
        return {}
    ports: dict[str, str] = {}
    port: str | None = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("Hardware Port:"):
            port = line.split(":", 1)[1].strip()
        elif line.startswith("Device:") and port:
            ports[port] = line.split(":", 1)[1].strip()
            port = None
    return ports


def detect_interface() -> str:
    """Return the Wi-Fi device name (e.g. en0) or raise when not found."""
    ports = list_interfaces()
    for name, device in ports.items():
        if "wi-fi" in name.lower():
            return device
    raise RuntimeError("no Wi-Fi interface found via networksetup")


def resolve_interface(cfg: Config) -> str:
    """Resolve the configured interface ('auto' -> detected Wi-Fi device)."""
    if cfg.interface == "auto":
        return detect_interface()
    return cfg.interface


def is_wifi_on(interface: str) -> bool:
    """Return True when the AirPort radio is powered on."""
    result = _run(["networksetup", "-getairportpower", interface], timeout=2)
    return "On" in result.stdout


def current_network(interface: str) -> str:
    """Return the SSID the interface is joined to, or the 'not connected' marker."""
    netsetup = "/usr/sbin/networksetup"
    result = _run([netsetup, "-getairportnetwork", interface], timeout=3)
    if result.returncode == 0:
        parts = result.stdout.split(": ")
        if len(parts) > 1:
            return parts[1].strip()
    return _NOT_CONNECTED


def current_mac(interface: str) -> str:
    """Return the current MAC address (uppercase) or 'Неизвестно'."""
    result = _run(["ifconfig", interface], timeout=3)
    for line in result.stdout.splitlines():
        if "ether" in line:
            return line.split("ether ")[1].split()[0].upper()
    return "Неизвестно"


def current_ip(interface: str) -> str:
    """Return the IPv4 address of the interface or 'Неизвестно'."""
    result = _run(["ipconfig", "getifaddr", interface], timeout=1)
    if result.returncode == 0:
        ip = result.stdout.strip()
        if ip:
            return ip
    return "Неизвестно"


def _ping_ms(host: str) -> float | None:
    result = _run(["ping", "-c", "1", "-W", "1500", host], timeout=3)
    if result.returncode != 0:
        return None
    match = re.search(r"time[=<]([\d.]+)\s*ms", result.stdout)
    if match:
        return float(match.group(1))
    return None


def average_ping_ms() -> float | None:
    """Average RTT to well-known hosts, or None when unreachable."""
    hosts = ("yandex.ru", "google.com")
    times = [_ping_ms(host) for host in hosts]
    valid = [t for t in times if t is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)


def saved_networks(interface: str) -> list[str]:
    """Return preferred (saved) networks seen via networksetup."""
    result = _run(
        ["networksetup", "-listpreferredwirelessnetworks", interface], timeout=3
    )
    if result.returncode != 0:
        return []
    lines = result.stdout.splitlines()
    return [line.strip() for line in lines[1:] if line.strip()]


def toggle_wifi(interface: str, turn_on: bool) -> bool:
    """Power the AirPort radio on/off; True on success."""
    state = "on" if turn_on else "off"
    try:
        _check(["networksetup", "-setairportpower", interface, state])
        return True
    except subprocess.CalledProcessError as exc:
        logger.error("toggle_wifi(%s) failed: %s", state, exc)
        return False


def wait_connected(interface: str, timeout: int = 30) -> bool:
    """Wait up to `timeout` seconds until Wi-Fi is on and joined to a network."""
    elapsed = 0
    while not is_wifi_on(interface) or current_network(interface) == _NOT_CONNECTED:
        time.sleep(1)
        elapsed += 1
        if elapsed > timeout:
            return False
    return True


def wifi_state(interface: str) -> WiFiState | None:
    """Snapshot the interface state; None when the radio is off."""
    if not is_wifi_on(interface):
        return None
    with ThreadPoolExecutor() as executor:
        net_f = executor.submit(current_network, interface)
        mac_f = executor.submit(current_mac, interface)
        ip_f = executor.submit(current_ip, interface)
        ping_f = executor.submit(average_ping_ms)
        return WiFiState(
            network=net_f.result(),
            mac=mac_f.result(),
            ip=ip_f.result(),
            ping_ms=ping_f.result(),
        )
