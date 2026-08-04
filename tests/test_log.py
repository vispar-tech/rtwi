from __future__ import annotations

import logging
from pathlib import Path

from rtwi import log as logmod


def test_get_logger() -> None:
    logger = logmod.get_logger("test")
    assert logger.name == "rtwi.test"
    assert isinstance(logger, logging.Logger)


def test_setup_logging(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(logmod, "LOG_PATH", tmp_path / "rtwi.log")
    root = logmod.setup_logging()
    assert root.handlers
    again = logmod.setup_logging(debug=True)
    assert again is root


def test_debug_enabled(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("RTWI_DEBUG", "1")
    assert logmod.debug_enabled() is True
    monkeypatch.setenv("RTWI_DEBUG", "0")
    assert logmod.debug_enabled() is False
