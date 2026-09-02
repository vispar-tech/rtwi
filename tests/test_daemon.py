from __future__ import annotations

import os
from pathlib import Path

from rtwi import daemon


def test_is_running(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(os, "kill", lambda _pid, _sig: None)
    assert daemon.is_running(123) is True
    monkeypatch.setattr(
        os, "kill", lambda _pid, _sig: (_ for _ in ()).throw(ProcessLookupError())
    )
    assert daemon.is_running(123) is False


def test_save_load_pid(tmp_path: Path) -> None:
    pid_path = tmp_path / "rtwi.daemon.pid"
    daemon.save_pid(42, path=pid_path)
    assert pid_path.read_text() == "42"
    assert daemon.load_pid(path=pid_path) == 42


def test_load_pid_missing(tmp_path: Path) -> None:
    assert daemon.load_pid(path=tmp_path / "missing") is None


def test_load_pid_invalid(tmp_path: Path) -> None:
    bad = tmp_path / "bad"
    bad.write_text("not-a-pid")
    assert daemon.load_pid(path=bad) is None


def test_stop_dead(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    pid_path = tmp_path / "rtwi.daemon.pid"
    daemon.save_pid(9999, path=pid_path)
    monkeypatch.setattr(daemon, "is_running", lambda _pid: False)
    assert daemon.stop(pid_path) is False


def test_start_spawns(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    pid_path = tmp_path / "rtwi.daemon.pid"
    monkeypatch.setattr(daemon.cfg, "LOG_PATH", tmp_path / "rtwi.log")

    class FakeProc:
        pid = 777

    monkeypatch.setattr(daemon.subprocess, "Popen", lambda *_a, **_k: FakeProc())
    monkeypatch.setattr(daemon, "_command", lambda _i: ["true"])
    daemon.start(interval=30, pid_path=pid_path)
    assert pid_path.read_text() == "777"
