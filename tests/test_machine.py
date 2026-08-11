from __future__ import annotations

from types import SimpleNamespace

from rtwi import auth, rollmac, wifi
from rtwi import machine as rtwi_machine
from rtwi.fix import FixResult, run_fix
from rtwi.machine import RTMachine
from rtwi.models import AuthResult, AuthState, Config

PHONE = "+79110000000"


def _config(**overrides: object) -> Config:
    return Config(phone=PHONE, **overrides)


def _machine(monkeypatch, cfg: Config) -> RTMachine:  # noqa: ANN001
    click = type("click", (), {})()
    monkeypatch.setattr(auth, "make_client", lambda _cfg: click)
    monkeypatch.setattr(
        wifi,
        "resolve_interface",
        lambda _cfg: "en0",
    )
    monkeypatch.setattr(wifi, "is_wifi_on", lambda _iface: True)
    monkeypatch.setattr(wifi, "current_network", lambda _iface: cfg.network)
    monkeypatch.setattr(wifi, "current_mac", lambda _iface: "02:00:00:00:00:01")
    monkeypatch.setattr(wifi, "current_ip", lambda _iface: "192.168.1.5")
    monkeypatch.setattr(wifi, "average_ping_ms", lambda: 12.3)
    return RTMachine(cfg)


def test_status(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config())
    monkeypatch.setattr(machine, "portal", lambda: AuthState.SUCCESS)
    wstate, portal = machine.status()
    assert wstate.network == "Rostelecom"
    assert wstate.mac == "02:00:00:00:00:01"
    assert wstate.ip == "192.168.1.5"
    assert wstate.ping_ms == 12.3
    assert portal == AuthState.SUCCESS


def test_connected_ok(monkeypatch) -> None:  # noqa: ANN001
    assert _machine(monkeypatch, _config()).connected() is True


def test_connected_wrong_network(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config())
    monkeypatch.setattr(wifi, "current_network", lambda _i: "Other")
    assert machine.connected() is False


def test_connected_wifi_off(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config())
    monkeypatch.setattr(wifi, "is_wifi_on", lambda _i: False)
    assert machine.connected() is False


def test_call_loop_immediate_success(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config())
    monkeypatch.setattr(
        auth,
        "confirm_call",
        lambda _c: AuthResult(AuthState.SUCCESS, "ok"),
    )
    result = machine.call_loop()
    assert result.state == AuthState.SUCCESS


def test_call_loop_polls_then_succeeds(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config(poll_interval=1, max_call_polls=5))
    calls = {call: AuthResult(AuthState.WAIT_CALL, "waiting") for call in range(3)}
    calls[3] = AuthResult(AuthState.SUCCESS, "picked up")

    def fake_check(_client: object) -> AuthResult:
        return calls.pop(len(calls), AuthResult(AuthState.SUCCESS, "picked up"))

    monkeypatch.setattr(auth, "confirm_call", fake_check)
    monkeypatch.setattr(rtwi_machine, "time", SimpleNamespace(sleep=lambda s: None))
    result = machine.call_loop()
    assert result.state == AuthState.SUCCESS


def test_call_loop_timeout(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config(poll_interval=1, max_call_polls=2))
    monkeypatch.setattr(
        auth,
        "confirm_call",
        lambda _c: AuthResult(AuthState.WAIT_CALL, "still waiting"),
    )
    monkeypatch.setattr(rtwi_machine, "time", SimpleNamespace(sleep=lambda s: None))
    result = machine.call_loop()
    assert result.state == AuthState.WAIT_CALL


def test_roll_requires_root(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config())
    monkeypatch.setattr(rollmac, "is_root", lambda: False)
    assert machine.roll() is None


def test_roll_root_run(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config())
    monkeypatch.setattr(rollmac, "is_root", lambda: True)
    monkeypatch.setattr(rollmac, "roll_mac", lambda _iface: "02:00:00:00:00:09")
    assert machine.roll() == "02:00:00:00:00:09"


def test_fix_offline(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config())
    monkeypatch.setattr(wifi, "is_wifi_on", lambda _i: False)
    result = run_fix(machine)
    assert result.state == AuthState.OFFLINE
    assert result.rolls == 0


def test_fix_success(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config())
    monkeypatch.setattr(
        machine,
        "auth",
        lambda: AuthResult(AuthState.SUCCESS, "done"),
    )
    result = run_fix(machine)
    assert result == FixResult(AuthState.SUCCESS, "done", 0)


def test_fix_wait_sms(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config(method="sms"))
    monkeypatch.setattr(
        machine,
        "auth",
        lambda: AuthResult(AuthState.WAIT_SMS, "awaiting code"),
    )
    result = run_fix(machine)
    assert result.state == AuthState.WAIT_SMS


def test_fix_wait_call_success(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config())
    monkeypatch.setattr(
        machine,
        "auth",
        lambda: AuthResult(AuthState.WAIT_CALL, "calling"),
    )
    monkeypatch.setattr(
        machine,
        "call_loop",
        lambda: AuthResult(AuthState.SUCCESS, "confirmed"),
    )
    result = run_fix(machine)
    assert result.state == AuthState.SUCCESS
    assert result.message == "confirmed"


def test_fix_wait_call_timeout(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config())
    monkeypatch.setattr(
        machine,
        "auth",
        lambda: AuthResult(AuthState.WAIT_CALL, "calling"),
    )
    monkeypatch.setattr(
        machine,
        "call_loop",
        lambda: AuthResult(AuthState.WAIT_CALL, "timeout"),
    )
    result = run_fix(machine)
    assert result.state == AuthState.WAIT_CALL


def test_fix_failed(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config())
    monkeypatch.setattr(
        machine,
        "auth",
        lambda: AuthResult(AuthState.FAILED, "portal error"),
    )
    result = run_fix(machine)
    assert result.state == AuthState.FAILED


def test_fix_forbidden_no_roll(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config(auto_roll=False))
    monkeypatch.setattr(
        machine,
        "auth",
        lambda: AuthResult(AuthState.FORBIDDEN, "limit"),
    )
    result = run_fix(machine)
    assert result.state == AuthState.FORBIDDEN
    assert result.rolls == 0


def test_fix_forbidden_rolls_then_success(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config(auto_roll=True, max_rolls=3))
    auth_results = iter(
        [
            AuthResult(AuthState.FORBIDDEN, "limit"),
            AuthResult(AuthState.SUCCESS, "done"),
        ]
    )
    monkeypatch.setattr(machine, "roll", lambda: "02:00:00:00:00:aa")
    monkeypatch.setattr(machine, "auth", lambda: next(auth_results))
    result = run_fix(machine)
    assert result.state == AuthState.SUCCESS
    assert result.rolls == 1


def test_fix_forbidden_rolls_exhausted(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config(auto_roll=True, max_rolls=2))
    monkeypatch.setattr(machine, "roll", lambda: "02:00:00:00:00:aa")
    monkeypatch.setattr(
        machine, "auth", lambda: AuthResult(AuthState.FORBIDDEN, "limit")
    )
    result = run_fix(machine)
    assert result.state == AuthState.FORBIDDEN
    assert result.rolls == 2


def test_fix_forbidden_roll_no_root(monkeypatch) -> None:  # noqa: ANN001
    machine = _machine(monkeypatch, _config(auto_roll=True, max_rolls=3))
    monkeypatch.setattr(machine, "roll", lambda: None)
    monkeypatch.setattr(
        machine,
        "auth",
        lambda: AuthResult(AuthState.FORBIDDEN, "limit"),
    )
    result = run_fix(machine)
    assert result.state == AuthState.FORBIDDEN
    assert "root" in result.message
    assert result.rolls == 0

    machine2 = _machine(monkeypatch, _config(auto_roll=True, max_rolls=1))
    roll_count = {"n": 0}

    def limited_roll() -> str | None:
        if roll_count["n"] >= 1:
            return None
        roll_count["n"] += 1
        return "02:00:00:00:00:bb"

    monkeypatch.setattr(machine2, "roll", limited_roll)
    monkeypatch.setattr(
        machine2,
        "auth",
        lambda: AuthResult(AuthState.FORBIDDEN, "limit"),
    )
    result2 = run_fix(machine2)
    assert result2.state == AuthState.FORBIDDEN
