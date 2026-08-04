from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from rtwi.models import Config

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]

__all__ = [
    "CONFIG_PATH",
    "LOG_PATH",
    "Config",
    "ConfigError",
    "load_config",
    "save_config",
]


class ConfigError(ValueError):
    """Raised when the config file cannot be read or validated."""


def _base_dir() -> Path:
    env = os.environ.get("RTWI_DIR")
    if env:
        return Path(env)
    return Path.home() / ".config" / "rtwi"


def _config_path() -> Path:
    env = os.environ.get("RTWI_CONFIG")
    if env:
        return Path(env)
    return _base_dir() / "config.yaml"


def _log_path() -> Path:
    return _base_dir() / "rtwi.log"


CONFIG_PATH = _config_path()
LOG_PATH = _log_path()


def _lock_for(path: Path) -> Path:
    return path.parent / (path.name + ".lock")


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    if fcntl is None:
        yield
        return
    lock_path = _lock_for(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _apply_env_overrides(cfg: Config) -> Config:
    if raw := os.environ.get("RTWI_PHONE"):
        cfg.phone = raw
    if raw := os.environ.get("RTWI_INTERFACE"):
        cfg.interface = raw
    if raw := os.environ.get("RTWI_METHOD"):
        cfg.method = raw
    if raw := os.environ.get("RTWI_NETWORK"):
        cfg.network = raw
    if raw := os.environ.get("RTWI_AUTO_ROLL"):
        cfg.auto_roll = raw.lower() in {"1", "true", "yes"}
    if raw := os.environ.get("RTWI_TIMEOUT"):
        cfg.request_timeout = int(raw)
    if raw := os.environ.get("RTWI_MAX_ROLLS"):
        cfg.max_rolls = int(raw)
    return cfg


def _load_unlocked(path: Path) -> Config:
    if not path.exists():
        cfg = Config()
        _save_unlocked(cfg, path)
        return _apply_env_overrides(cfg)
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    try:
        return _apply_env_overrides(Config(**data))
    except ValidationError as exc:
        raise ConfigError(f"invalid configuration in {path}:\n{exc}") from exc


def _save_unlocked(cfg: Config, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.safe_dump(cfg.model_dump(mode="json"), f)
        Path(tmp).replace(path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Load configuration, creating a default one (with env overrides) if missing."""
    with _file_lock(path):
        return _load_unlocked(path)


def save_config(cfg: Config, path: Path = CONFIG_PATH) -> None:
    """Atomically write configuration to `path` (temp file + rename)."""
    with _file_lock(path):
        _save_unlocked(cfg, path)
