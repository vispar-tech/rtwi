from __future__ import annotations

import re
import subprocess
from types import SimpleNamespace

import pytest

from rtwi import rollmac, wifi
from rtwi.rollmac import RollMACError


def _toggle_true(_iface: str, turn_on: bool) -> bool:
    return True


def _toggle_false(_iface: str, turn_on: bool) -> bool:
    return False


def _mk_toggler() -> tuple[list[bool], object]:
    """Return (history, stub) where the stub records (turn_on) calls and wins.

    The stub always returns True so off and on both succeed.
    """

    def toggle(_iface: str, turn_on: bool) -> bool:
        history.append(turn_on)
        return True

    history: list[bool] = []
    return history, toggle


def test_random_mac_format() -> None:
    mac = rollmac.random_mac()
    assert re.match(r"^02:[0-9a-f]{2}(:[0-9a-f]{2}){4}$", mac)


def test_random_mac_unicity() -> None:
    macs = {rollmac.random_mac() for _ in range(100)}
    assert len(macs) == 100


def test_change_mac_sequence(monkeypatch) -> None:  # noqa: ANN001
    calls: list[list[str]] = []
    monkeypatch.setattr(wifi, "toggle_wifi", _toggle_true)

    def fake_check(args: list[str], **kwargs: object) -> None:
        calls.append(args)

    monkeypatch.setattr(subprocess, "check_call", fake_check)
    rollmac.change_mac("en0", "02:AA:BB:CC:DD:EE")
    assert calls == [
        [rollmac._AIRPORT, "-z"],
        ["ifconfig", "en0", "ether", "02:aa:bb:cc:dd:ee"],
        ["networksetup", "-detectnewhardware"],
    ]


def test_change_mac_power_failure(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(wifi, "toggle_wifi", _toggle_false)
    with pytest.raises(RollMACError, match="power the Wi-Fi radio on"):
        rollmac.change_mac("en0", "02:00:00:00:00:01")


def test_change_mac_command_failure(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(wifi, "toggle_wifi", _toggle_true)

    def boom(args: list[str], **kwargs: object) -> None:
        raise subprocess.CalledProcessError(-1, args)

    monkeypatch.setattr(subprocess, "check_call", boom)
    with pytest.raises(RollMACError, match="MAC change failed"):
        rollmac.change_mac("en0", "02:00:00:00:00:01")


def test_roll_mac_flow(monkeypatch) -> None:  # noqa: ANN001
    history, toggle = _mk_toggler()
    monkeypatch.setattr(wifi, "toggle_wifi", toggle)
    monkeypatch.setattr(rollmac, "time", SimpleNamespace(sleep=lambda s: None))
    monkeypatch.setattr(rollmac, "random_mac", lambda: "02:00:00:00:00:42")
    monkeypatch.setattr(wifi, "current_mac", lambda _iface: "02:00:00:00:00:99")
    monkeypatch.setattr(subprocess, "check_call", lambda *a, **k: None)
    monkeypatch.setattr(wifi, "wait_connected", lambda *a, **k: True)
    assert rollmac.roll_mac("en0") == "02:00:00:00:00:42"
    assert history == [False, True, True]


def test_roll_mac_regenerates_on_collision(monkeypatch) -> None:  # noqa: ANN001
    random_values = iter(["02:00:00:00:00:42", "02:00:00:00:00:43"])
    monkeypatch.setattr(rollmac, "time", SimpleNamespace(sleep=lambda s: None))
    monkeypatch.setattr(rollmac, "random_mac", lambda: next(random_values))
    monkeypatch.setattr(wifi, "current_mac", lambda _iface: "02:00:00:00:00:42")
    monkeypatch.setattr(wifi, "toggle_wifi", _toggle_true)
    monkeypatch.setattr(subprocess, "check_call", lambda *a, **k: None)
    monkeypatch.setattr(wifi, "wait_connected", lambda *a, **k: True)
    assert rollmac.roll_mac("en0") == "02:00:00:00:00:43"


def test_roll_mac_off_failure(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(wifi, "toggle_wifi", _toggle_false)
    with pytest.raises(RollMACError, match="radio off"):
        rollmac.roll_mac("en0")


def test_roll_mac_reconnect_failure(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(rollmac, "time", SimpleNamespace(sleep=lambda s: None))
    monkeypatch.setattr(wifi, "toggle_wifi", _toggle_true)
    monkeypatch.setattr(rollmac, "random_mac", lambda: "02:00:00:00:00:44")
    monkeypatch.setattr(wifi, "current_mac", lambda _iface: "02:00:00:00:00:99")
    monkeypatch.setattr(subprocess, "check_call", lambda *a, **k: None)
    monkeypatch.setattr(wifi, "wait_connected", lambda *a, **k: False)
    with pytest.raises(RollMACError, match="did not reconnect"):
        rollmac.roll_mac("en0")


def test_roll_mac_on_failure(monkeypatch) -> None:  # noqa: ANN001
    on_calls = 0

    def toggle(_iface: str, turn_on: bool) -> bool:
        nonlocal on_calls
        if not turn_on:
            return True  # off succeeds
        on_calls += 1  # first on (in change_mac) ok, second (roll) fails
        return on_calls == 1

    monkeypatch.setattr(rollmac, "time", SimpleNamespace(sleep=lambda s: None))
    monkeypatch.setattr(wifi, "toggle_wifi", toggle)
    monkeypatch.setattr(rollmac, "random_mac", lambda: "02:00:00:00:00:44")
    monkeypatch.setattr(wifi, "current_mac", lambda _iface: "02:00:00:00:00:99")
    monkeypatch.setattr(subprocess, "check_call", lambda *a, **k: None)
    monkeypatch.setattr(wifi, "wait_connected", lambda *a, **k: True)
    with pytest.raises(RollMACError, match="radio back on"):
        rollmac.roll_mac("en0")


def test_is_root(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(rollmac.os, "geteuid", lambda: 0)
    assert rollmac.is_root() is True
    monkeypatch.setattr(rollmac.os, "geteuid", lambda: 501)
    assert rollmac.is_root() is False


def test_binary_command_frozen(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(rollmac.sys, "frozen", True, raising=False)
    monkeypatch.setattr(rollmac.sys, "executable", "/usr/local/bin/rtwi")
    assert rollmac._binary_command() == ["/usr/local/bin/rtwi"]


def test_binary_command_source(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(rollmac.sys, "frozen", False, raising=False)
    monkeypatch.setattr(rollmac.sys, "executable", "/usr/bin/python3.14")
    assert rollmac._binary_command() == ["/usr/bin/python3.14", "-m", "rtwi"]


def test_self_elevate_sudo(monkeypatch) -> None:  # noqa: ANN001
    calls: list[list[str]] = []
    monkeypatch.setattr(rollmac, "_binary_command", lambda: ["/bin/rtwi"])

    def fake_run(args: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert rollmac.self_elevate(["roll"]) == 0
    assert calls == [["sudo", "--", "/bin/rtwi", "roll"]]


def test_self_elevate_gui_prompt(monkeypatch) -> None:  # noqa: ANN001
    calls: list[list[str]] = []
    monkeypatch.setattr(rollmac, "_binary_command", lambda: ["/bin/rtwi"])

    def fake_run(args: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert rollmac.self_elevate(["roll"], gui_prompt=True) == 0
    assert calls[0][0] == "osascript"
    assert "with administrator privileges" in calls[0][-1]
