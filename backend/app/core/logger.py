"""
Centralised logging configuration for the Agentic Web IDE backend.

Supports two modes:
  - Development (default): colored human-readable output
  - Production (LOG_FORMAT=json): structured JSON for log aggregation

Correlation IDs are injected via contextvars so every log line within a
pipeline run can be traced back to the originating request.

Usage:
    from app.core.logger import get_logger, set_correlation_id
    log = get_logger(__name__)
    set_correlation_id("abc123")
    log.info("message")  # includes correlation_id in output
"""

import json as _json
import logging
import os
import sys
import time
from contextvars import ContextVar

# ── Correlation ID ────────────────────────────────────────────────────

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID for the current async context."""
    _correlation_id.set(cid)


def get_correlation_id() -> str:
    return _correlation_id.get()


# ── Formatters ────────────────────────────────────────────────────────

class _DevFormatter(logging.Formatter):
    """Colored, human-readable output for development."""
    LEVEL_COLORS = {
        "DEBUG":    "\033[36m",   # cyan
        "INFO":     "\033[32m",   # green
        "WARNING":  "\033[33m",   # yellow
        "ERROR":    "\033[31m",   # red
        "CRITICAL": "\033[35m",   # magenta
    }
    RESET = "\033[0m"
    BOLD  = "\033[1m"

    def format(self, record: logging.LogRecord) -> str:
        color  = self.LEVEL_COLORS.get(record.levelname, "")
        level  = f"{color}{record.levelname:<8}{self.RESET}"
        name   = record.name.split(".")[-1]
        name   = f"{self.BOLD}{name:<18}{self.RESET}"
        ts     = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        ms     = f"{record.msecs:03.0f}"
        cid    = _correlation_id.get()
        cid_str = f" [{cid[:8]}]" if cid != "-" else ""
        return f"{ts}.{ms} | {level} | {name} |{cid_str} {record.getMessage()}"


class _JSONFormatter(logging.Formatter):
    """Structured JSON output for production log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S") + f".{record.msecs:03.0f}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": _correlation_id.get(),
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return _json.dumps(log_entry)


# ── Setup ─────────────────────────────────────────────────────────────

def _setup_root_logger() -> None:
    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    handler = logging.StreamHandler(sys.stdout)

    log_format = os.getenv("LOG_FORMAT", "dev").lower()
    if log_format == "json":
        handler.setFormatter(_JSONFormatter())
    else:
        handler.setFormatter(_DevFormatter())

    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Quieten noisy third-party loggers
    for noisy in ("httpx", "httpcore", "openai", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


_setup_root_logger()


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Pass __name__ from the calling module."""
    return logging.getLogger(name)


# ── Timing helper ─────────────────────────────────────────────────────

class Timer:
    """Simple context manager / manual timer that returns elapsed seconds."""

    def __init__(self) -> None:
        self._start = time.perf_counter()

    def elapsed(self) -> float:
        return round(time.perf_counter() - self._start, 2)

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_):
        pass
