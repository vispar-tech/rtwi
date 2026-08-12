from __future__ import annotations

from types import SimpleNamespace

from typer.testing import CliRunner

from rtwi import cli, rollmac
from rtwi import config as cfg
from rtwi.models import AuthResult, AuthState, WiFiState

runner = CliRunner()

PHONE = "+79110000000"


class FakeMachine:
    def __init__(
        self,
        *,
        status: tuple[WiFiState, AuthState] | None = None,
        sms_result: AuthResult | None = None,
        roll_result: str | None = None,
        roll_error: Exception | None = None,
        fix_result: object | None = None,
        config: object | None = None,
    ) -> None:
        self._status = status
        self.sms_result = sms_result or AuthResult(AuthState.SUCCESS, "ok")
        self.roll_result = roll_result
        self.roll_error = roll_error
        self.fix_result = fix_result or SimpleNamespace(
            state=AuthState.SUCCESS, message="done", rolls=0
        )
        self.config = config or SimpleNamespace(
            auto_roll=True, max_rolls=2, phone=PHONE, method="call"
        )

    def status(self) -> tuple[WiFiState, AuthState]:
        assert self._status is not None
        return self._status

    def sms(self, _code: str) -> AuthResult:
        return self.sms_result

    def roll(self) -> str | None:
        if self.roll_error:
            raise self.roll_error
        return self.roll_result

    def connected(self) -> bool:
        return True

    def auth(self) -> AuthResult:
        return AuthResult(AuthState.SUCCESS, "done")

    def call_loop(self) -> AuthResult:
        return AuthResult(AuthState.SUCCESS, "confirmed")


def _wstate(**overrides: object) -> WiFiState:
    data = {
        "network": "Rostelecom",
        "mac": "02:00:00:00:00:01",
        "ip": "192.168.1.5",
        "ping_ms": 12.3,
    }
    data.update(overrides)
    return WiFiState(**data)


def run(*args: str, **kwargs: object) -> object:
    return runner.invoke(cli.app, list(args), **kwargs)


def test_version() -> None:
    result = run("--version")
    assert result.exit_code == 0
    assert "rtwi " in result.stdout


def test_status_table(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        cli,
        "_make_machine",
        lambda: FakeMachine(status=(_wstate(), AuthState.SUCCESS)),
    )
    result = run("status")
    assert result.exit_code == 0
    assert "Rostelecom" in result.stdout
    assert "authorized" in result.stdout


def test_status_json(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        cli,
        "_make_machine",
        lambda: FakeMachine(status=(_wstate(ping_ms=None, ip=""), AuthState.NEED_AUTH)),
    )
    result = run("status", "--json")
    assert result.exit_code == 0
    assert '"portal": "need_auth"' in result.stdout


def test_status_interface_error(monkeypatch) -> None:  # noqa: ANN001
    def boom() -> FakeMachine:
        machine = FakeMachine(status=(_wstate(), AuthState.SUCCESS))
        machine.status = lambda: (_ for _ in ()).throw(  # type: ignore[assignment]
            RuntimeError("no Wi-Fi interface found")
        )
        return machine

    monkeypatch.setattr(cli, "_make_machine", boom)
    result = run("status")
    assert result.exit_code == 1
    assert "no Wi-Fi interface" in result.stdout


def test_fix_success(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(cli, "_make_machine", lambda: FakeMachine())
    monkeypatch.setattr(
        cli,
        "run_fix",
        lambda _m: SimpleNamespace(state=AuthState.SUCCESS, message="done", rolls=1),
    )
    result = run("fix")
    assert result.exit_code == 0
    assert "authorized" in result.stdout
    assert "mac rolled: 1 time(s)" in result.stdout


def test_fix_wait_sms(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(cli, "_make_machine", lambda: FakeMachine())
    monkeypatch.setattr(
        cli,
        "run_fix",
        lambda _m: SimpleNamespace(
            state=AuthState.WAIT_SMS, message="SMS required", rolls=0
        ),
    )
    result = run("fix")
    assert result.exit_code == 2
    assert "SMS required" in result.stdout


def test_fix_offline(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(cli, "_make_machine", lambda: FakeMachine())
    monkeypatch.setattr(
        cli,
        "run_fix",
        lambda _m: SimpleNamespace(state=AuthState.OFFLINE, message="offline", rolls=0),
    )
    result = run("fix")
    assert result.exit_code == 5
    assert "offline" in result.stdout


def test_fix_sudo_elevates(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(rollmac, "is_root", lambda: False)
    elevated: list[list[str]] = []
    monkeypatch.setattr(rollmac, "self_elevate", lambda cmd: elevated.append(cmd) or 0)
    result = run("fix", "--sudo")
    assert result.exit_code == 0
    assert elevated == [["fix", "--sudo"]]


def test_fix_sudo_as_root(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(rollmac, "is_root", lambda: True)
    monkeypatch.setattr(cli, "_make_machine", lambda: FakeMachine())
    result = run("fix", "--sudo")
    assert result.exit_code == 0
    assert "authorized" in result.stdout


def test_sms(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        cli,
        "_make_machine",
        lambda: FakeMachine(
            sms_result=AuthResult(AuthState.SUCCESS, "authorized over sms")
        ),
    )
    result = run("sms", "1234")
    assert result.exit_code == 0
    assert "authorized over sms" in result.stdout


def test_sms_rejected(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        cli,
        "_make_machine",
        lambda: FakeMachine(sms_result=AuthResult(AuthState.WAIT_SMS, "rejected")),
    )
    result = run("sms", "0000")
    assert result.exit_code == 2
    assert "rejected" in result.stdout


def test_roll_success(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        cli,
        "_make_machine",
        lambda: FakeMachine(roll_result="02:00:00:00:00:42"),
    )
    result = run("roll")
    assert result.exit_code == 0
    assert "02:00:00:00:00:42" in result.stdout


def test_roll_requires_root(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(cli, "_make_machine", lambda: FakeMachine(roll_result=None))
    result = run("roll")
    assert result.exit_code == 1
    assert "--sudo" in result.stdout


def test_roll_error(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        cli,
        "_make_machine",
        lambda: FakeMachine(roll_error=rollmac.RollMACError("boom")),
    )
    result = run("roll")
    assert result.exit_code == 1
    assert "boom" in result.stdout


def test_roll_sudo_elevates(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(rollmac, "is_root", lambda: False)
    elevated: list[list[str]] = []
    monkeypatch.setattr(rollmac, "self_elevate", lambda cmd: elevated.append(cmd) or 0)
    result = run("roll", "--sudo")
    assert result.exit_code == 0
    assert elevated == [["roll", "--sudo"]]


def test_config_opens_editor(monkeypatch) -> None:  # noqa: ANN001
    calls: list[list[str]] = []
    monkeypatch.setattr(cfg, "CONFIG_PATH", cfg.CONFIG_PATH)  # keep default
    monkeypatch.setattr(cfg, "load_config", lambda: None)
    import subprocess as _sp

    def fake_run(args: list[str], **kwargs: object) -> object:
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(_sp, "run", fake_run)
    monkeypatch.setenv("EDITOR", "nano")
    result = run("config", input="")
    assert result.exit_code == 0
    assert calls == [["nano", str(cfg.CONFIG_PATH)]]
