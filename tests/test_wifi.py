from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from rtwi import wifi
from rtwi.models import Config


def _cp(stdout: str = "", stderr: str = "", code: int = 0) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=code)


def _fake_run(stdout: str = "", code: int = 0) -> object:
    """Build a `_run` stub returning a fixed CompletedProcess."""

    def fake(_args: list[str], timeout: float = 5) -> SimpleNamespace:
        return _cp(stdout=stdout, code=code)

    return fake


def test_list_interfaces(monkeypatch) -> None:  # noqa: ANN001
    out = (
        "Hardware Port: Wi-Fi\nDevice: en0\nEthernet Address: aa:bb\n\n"
        "Hardware Port: Thunderbolt Bridge\nDevice: bridge0\n"
    )
    monkeypatch.setattr(wifi, "_run", _fake_run(stdout=out))
    assert wifi.list_interfaces() == {"Wi-Fi": "en0", "Thunderbolt Bridge": "bridge0"}


def test_list_interfaces_failure(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(wifi, "_run", _fake_run(code=1, stdout="boom err"))
    assert wifi.list_interfaces() == {}


def test_detect_interface(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(wifi, "list_interfaces", lambda: {"Wi-Fi": "en0"})
    assert wifi.detect_interface() == "en0"


def test_detect_interface_missing(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(wifi, "list_interfaces", lambda: {"Ethernet": "en5"})
    with pytest.raises(RuntimeError, match="Wi-Fi interface"):
        wifi.detect_interface()


def test_resolve_interface_auto(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(wifi, "detect_interface", lambda: "en0")
    assert wifi.resolve_interface(Config()) == "en0"


def test_resolve_interface_explicit() -> None:
    assert wifi.resolve_interface(Config(interface="en1")) == "en1"


def test_is_wifi_on(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(wifi, "_run", _fake_run(stdout="Wi-Fi Power (en0): On"))
    assert wifi.is_wifi_on("en0") is True
    monkeypatch.setattr(wifi, "_run", _fake_run(stdout="Wi-Fi Power (en0): Off"))
    assert wifi.is_wifi_on("en0") is False


def test_current_network(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        wifi, "_run", _fake_run(stdout="Current Wi-Fi Network: Rostelecom")
    )
    assert wifi.current_network("en0") == "Rostelecom"


def test_current_network_not_connected(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(wifi, "_run", _fake_run(code=1))
    assert wifi.current_network("en0") == wifi._NOT_CONNECTED


def test_current_mac(monkeypatch) -> None:  # noqa: ANN001
    out = "\n".join(
        ["en0: flags=...", "\tether 02:aa:bb:cc:dd:ee ", "\tinet 192.168.1.5"]
    )
    monkeypatch.setattr(wifi, "_run", _fake_run(stdout=out))
    assert wifi.current_mac("en0") == "02:AA:BB:CC:DD:EE"


def test_current_mac_unknown(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(wifi, "_run", _fake_run(code=1))
    assert wifi.current_mac("en0") == "Неизвестно"


def test_current_ip(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(wifi, "_run", _fake_run("192.168.1.5\n"))
    assert wifi.current_ip("en0") == "192.168.1.5"


def test_current_ip_unknown(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(wifi, "_run", _fake_run(code=1))
    assert wifi.current_ip("en0") == "Неизвестно"


def test_average_ping_ms(monkeypatch) -> None:  # noqa: ANN001
    def fake(args: list[str], timeout: float = 5) -> SimpleNamespace:
        if args[-1] == "yandex.ru":
            return _cp("64 bytes from ... time=12.3 ms")
        return _cp("64 bytes from ... time=13.5 ms")

    monkeypatch.setattr(wifi, "_run", fake)
    assert wifi.average_ping_ms() == pytest.approx(12.9)


def test_average_ping_ms_unreachable(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(wifi, "_run", _fake_run(code=1))
    assert wifi.average_ping_ms() is None


def test_saved_networks(monkeypatch) -> None:  # noqa: ANN001
    out = "Preferred networks on en0:\n    Rostelecom\n    HOME\n"
    monkeypatch.setattr(wifi, "_run", _fake_run(stdout=out))
    assert wifi.saved_networks("en0") == ["Rostelecom", "HOME"]


def test_toggle_wifi_ok(monkeypatch) -> None:  # noqa: ANN001
    calls: list[list[str]] = []

    def fake_check(args: list[str], timeout: float = 5) -> None:
        calls.append(args)

    monkeypatch.setattr(wifi, "_check", fake_check)
    assert wifi.toggle_wifi("en0", False) is True
    assert calls == [["networksetup", "-setairportpower", "en0", "off"]]


def test_toggle_wifi_failure(monkeypatch) -> None:  # noqa: ANN001
    def boom(_args: list[str], _timeout: float = 5) -> None:
        raise subprocess.CalledProcessError(-1, "networksetup")

    monkeypatch.setattr(wifi, "_check", boom)
    assert wifi.toggle_wifi("en0", True) is False


def test_wait_connected(monkeypatch) -> None:  # noqa: ANN001
    states = iter([(True, "Не подключено"), (True, "Не подключено"), (True, "RT")])

    def fake_net(_iface: str) -> str:
        return next(states)[1]

    monkeypatch.setattr(wifi, "is_wifi_on", lambda *a: True)
    monkeypatch.setattr(wifi, "current_network", fake_net)
    monkeypatch.setattr(wifi, "time", SimpleNamespace(sleep=lambda s: None))
    assert wifi.wait_connected("en0", timeout=3) is True


def test_wait_connected_timeout(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(wifi, "is_wifi_on", lambda *a: False)
    monkeypatch.setattr(wifi, "current_network", lambda *a: wifi._NOT_CONNECTED)
    monkeypatch.setattr(wifi, "time", SimpleNamespace(sleep=lambda s: None))
    assert wifi.wait_connected("en0", timeout=2) is False


def test_wifi_state_off(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(wifi, "is_wifi_on", lambda *a: False)
    assert wifi.wifi_state("en0") is None


def test_wifi_state_snapshot(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(wifi, "is_wifi_on", lambda *a: True)
    monkeypatch.setattr(wifi, "current_network", lambda *a: "RT")
    monkeypatch.setattr(wifi, "current_mac", lambda *a: "02:AA")
    monkeypatch.setattr(wifi, "current_ip", lambda *a: "10.0.0.2")
    monkeypatch.setattr(wifi, "average_ping_ms", lambda: 9.5)
    state = wifi.wifi_state("en0")
    assert state is not None
    assert (state.network, state.mac, state.ip, state.ping_ms) == (
        "RT",
        "02:AA",
        "10.0.0.2",
        9.5,
    )
