from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


class ISTFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=IST)
        return dt.strftime(datefmt or "%Y-%m-%d %H:%M:%S %Z")


def setup_logger(log_dir: Path, backup_days: int) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("file_monitor")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = ISTFormatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = TimedRotatingFileHandler(
        filename=log_dir / "monitor.log",
        when="midnight",
        backupCount=backup_days,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False
    return logger
