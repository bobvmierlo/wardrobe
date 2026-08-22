"""Application logging.

Two sinks, one configuration:

* **stdout** — plain, greppable lines that end up in ``docker compose logs``.
* **an in-memory ring buffer** — the last few hundred records, so an admin can
  read the same log straight from the app (Instellingen → Logboek) without
  shell access to the server.

The buffer is deliberately small and volatile: it is a live troubleshooting
view, not an archive. Anything that must survive a restart is written to the
``audit_logs`` table instead (see :mod:`app.audit`).
"""

from __future__ import annotations

import logging
import sys
from collections import deque
from datetime import datetime, timezone
from threading import Lock

# Every logger the app creates hangs under this name, so one handler catches
# them all and third-party noise (uvicorn, sqlalchemy) stays separate.
ROOT_LOGGER = "kledingkast"

LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# How many records the in-app view keeps. ~500 lines is a few minutes of busy
# use and costs well under a megabyte.
BUFFER_SIZE = 500


class RingBufferHandler(logging.Handler):
    """Keeps the most recent records in memory for the admin log screen."""

    def __init__(self, capacity: int = BUFFER_SIZE) -> None:
        super().__init__()
        self._records: deque[dict] = deque(maxlen=capacity)
        self._lock = Lock()
        self._seq = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            if record.exc_info:
                message = f"{message}\n{self.format(record)}"
        except Exception:  # pragma: no cover - never let logging break a request
            message = "<onleesbare logregel>"
        with self._lock:
            self._seq += 1
            self._records.append(
                {
                    "id": self._seq,
                    "time": datetime.fromtimestamp(record.created, tz=timezone.utc),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": message,
                }
            )

    def snapshot(self, limit: int = 200, min_level: str | None = None) -> list[dict]:
        """The newest records first, optionally only at ``min_level`` or worse."""
        threshold = logging.getLevelName(min_level.upper()) if min_level else 0
        if not isinstance(threshold, int):
            threshold = 0
        with self._lock:
            records = list(self._records)
        if threshold:
            records = [
                r for r in records
                if _level_value(r["level"]) >= threshold
            ]
        return list(reversed(records))[:limit]

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


def _level_value(name: str) -> int:
    value = logging.getLevelName(name)
    return value if isinstance(value, int) else 0


buffer_handler = RingBufferHandler()


def configure_logging(level: str = "INFO") -> None:
    """Attach the stdout and ring-buffer handlers exactly once."""
    logger = logging.getLogger(ROOT_LOGGER)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Uvicorn configures the root logger itself; keep our lines from being
    # printed twice by not propagating up to it.
    logger.propagate = False
    if logger.handlers:
        return

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    buffer_handler.setFormatter(formatter)
    logger.addHandler(buffer_handler)


def get_logger(name: str) -> logging.Logger:
    """A logger under the app's namespace, e.g. ``get_logger("items")``."""
    return logging.getLogger(f"{ROOT_LOGGER}.{name}")
