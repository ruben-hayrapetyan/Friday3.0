"""The daemon's log file (M16): `data_dir/logs/fridayd.log`, rotated at 5 MB, five kept. Every command with its actor
and time, every plan with its reason, seconds and outcome, syncs that brought something in, what the app reported
from your screen, and every error with its traceback, so a morning that went wrong can be read back. The commands
and plans are in the database too (`friday diagnose` reads them back); the file adds timings, errors and order."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
LOGGERS = ("friday", "uvicorn.error")


def install(data_dir: Path, level: str) -> Path:
    folder = data_dir / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "fridayd.log"
    handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter(FORMAT))
    for name in LOGGERS:
        logger = logging.getLogger(name)
        logger.setLevel(level.upper())
        if not any(isinstance(h, RotatingFileHandler) and h.baseFilename == str(path) for h in logger.handlers):
            logger.addHandler(handler)
    return path
