"""
Centralised logging configuration for the Agentic Web IDE backend.

Usage in any module:
    from app.core.logger import get_logger
    log = get_logger(__name__)
    log.info("message")

Format:
    2024-03-15 14:23:01.456 | INFO     | planner          | Planning for: build a form...
"""

import logging
import sys
import time


# ── Formatter ───────────────────────────────────────────────────────
class _Formatter(logging.Formatter):
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
        # Shorten module name for readability: app.agents.planner → planner
        name   = record.name.split(".")[-1]
        name   = f"{self.BOLD}{name:<18}{self.RESET}"
        ts     = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        ms     = f"{record.msecs:03.0f}"
        return f"{ts}.{ms} | {level} | {name} | {record.getMessage()}"


# ── Setup ────────────────────────────────────────────────────────────
def _setup_root_logger() -> None:
    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_Formatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Quieten noisy third-party loggers
    for noisy in ("httpx", "httpcore", "openai", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


_setup_root_logger()


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Pass __name__ from the calling module."""
    return logging.getLogger(name)


# ── Timing helper ────────────────────────────────────────────────────
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
