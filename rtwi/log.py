from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

from rtwi.config import LOG_PATH

_ROOT_NAME = "rtwi"


def setup_logging(debug: bool = False) -> logging.Logger:
    """Configure the package root logger: rotating file + rich console on stderr.

    The file handler always writes; the console handler is enabled only for
    debug runs (RTWI_DEBUG=1 or --debug) so user-facing rich output stays clean.
    """
    root = logging.getLogger(_ROOT_NAME)
    if root.handlers:
        return root
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    Path(LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root.addHandler(file_handler)
    if debug:
        console_handler = RichHandler(
            rich_tracebacks=True, show_time=False, show_path=False
        )
        root.addHandler(console_handler)
    return root


def debug_enabled() -> bool:
    """Return True when RTWI_DEBUG is set to a truthy value."""
    return os.environ.get("RTWI_DEBUG", "0").lower() in {"1", "true", "yes"}


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the rtwi root."""
    return logging.getLogger(f"{_ROOT_NAME}.{name}")
