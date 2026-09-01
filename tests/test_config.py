from __future__ import annotations

from datetime import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from rtwi.config import ConfigError, load_config, save_config
from rtwi.models import Config


def test_defaults(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg.phone is None
    assert cfg.interface == "auto"
    assert cfg.method == "call"
    assert cfg.network == "Rostelecom"
    assert cfg.auto_roll is True
    assert cfg.max_rolls == 3
    assert cfg.request_timeout == 5
    assert cfg.poll_interval == 5
    assert cfg.max_call_polls == 10
    assert cfg.user_agent.startswith("rtwi/")


def test_save_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    cfg = Config(phone="+79118293291", method="sms", max_rolls=5)
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.phone == "+79118293291"
    assert loaded.method == "sms"
    assert loaded.max_rolls == 5
    assert loaded.interface == "auto"


def test_bad_phone_rejected() -> None:
    with pytest.raises(ValidationError):
        Config(phone="79118293291")


def test_empty_phone_allowed() -> None:
    assert Config(phone="").phone is None


def test_bad_method_rejected() -> None:
    with pytest.raises(ValidationError):
        Config(method="push")


def test_max_rolls_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Config(max_rolls=0)


def test_corrupt_yaml(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(": bad: [yaml\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_env_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "config.yaml"
    monkeypatch.setenv("RTWI_PHONE", "+79995556677")
    monkeypatch.setenv("RTWI_INTERFACE", "en1")
    monkeypatch.setenv("RTWI_METHOD", "sms")
    monkeypatch.setenv("RTWI_AUTO_ROLL", "0")
    monkeypatch.setenv("RTWI_TIMEOUT", "8")
    monkeypatch.setenv("RTWI_MAX_ROLLS", "7")
    cfg = load_config(path)
    assert cfg.phone == "+79995556677"
    assert cfg.interface == "en1"
    assert cfg.method == "sms"
    assert cfg.auto_roll is False
    assert cfg.request_timeout == 8
    assert cfg.max_rolls == 7


def test_load_missing_creates_file(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    load_config(path)
    assert path.exists()
    with path.open() as f:
        data = f.read()
    assert "network: Rostelecom" in data


def test_schedule_in_yaml_roundtrip(tmp_path: Path) -> None:
    from rtwi.models import Schedule

    path = tmp_path / "config.yaml"
    cfg = Config(
        schedule=Schedule(
            enabled=True, start=time(7, 0), end=time(19, 0), days=[1, 3, 5]
        )
    )
    from rtwi.config import save_config

    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.schedule.enabled is True
    assert loaded.schedule.start.hour == 7
    assert loaded.schedule.end.hour == 19
    assert loaded.schedule.days == [1, 3, 5]
