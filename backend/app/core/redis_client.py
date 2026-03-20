"""
Redis client — manages active sessions and real-time state.

Gracefully degrades: if Redis is unavailable, all operations return None/no-op
so the app falls back to SQLite for everything. Performance suffers but nothing breaks.
"""

from __future__ import annotations

import json
from functools import wraps
from typing import Any, Callable

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger(__name__)

_pool: aioredis.Redis | None = None
_available: bool = True  # Tracks whether Redis is reachable


def _graceful(default: Any = None) -> Callable:
    """Decorator: catch Redis errors, log once, return a safe default."""
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            global _available
            try:
                result = await fn(*args, **kwargs)
                if not _available:
                    log.info("Redis connection restored")
                    _available = True
                return result
            except (
                aioredis.ConnectionError,
                aioredis.TimeoutError,
                ConnectionRefusedError,
                OSError,
            ) as e:
                if _available:
                    log.warning(f"Redis unavailable — falling back to SQLite: {e}")
                    _available = False
                return default
        return wrapper
    return decorator


def _key(session_id: str, suffix: str = "") -> str:
    return f"session:{session_id}{':' + suffix if suffix else ''}"


async def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=20,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
    return _pool


async def close_redis() -> None:
    global _pool
    if _pool:
        try:
            await _pool.aclose()
        except Exception:
            pass
        _pool = None


def is_available() -> bool:
    """Check if Redis is currently reachable (last-known state)."""
    return _available


# ── Session operations ────────────────────────────────────────────────

@_graceful()
async def save_session(session_id: str, data: dict) -> None:
    """Cache session metadata in Redis with TTL."""
    r = await get_redis()
    await r.set(
        _key(session_id, "meta"),
        json.dumps(data),
        ex=settings.SESSION_CACHE_TTL,
    )


@_graceful()
async def get_session(session_id: str) -> dict | None:
    """Fetch cached session metadata. Returns None if expired/missing."""
    r = await get_redis()
    raw = await r.get(_key(session_id, "meta"))
    if raw:
        return json.loads(raw)
    return None


@_graceful()
async def save_session_files(session_id: str, files: dict[str, str]) -> None:
    """Cache the current file state for a session."""
    r = await get_redis()
    await r.set(
        _key(session_id, "files"),
        json.dumps(files),
        ex=settings.SESSION_CACHE_TTL,
    )


@_graceful()
async def get_session_files(session_id: str) -> dict[str, str] | None:
    """Fetch cached files for a session."""
    r = await get_redis()
    raw = await r.get(_key(session_id, "files"))
    if raw:
        return json.loads(raw)
    return None


@_graceful()
async def touch_session(session_id: str) -> None:
    """Refresh TTL on all keys for this session."""
    r = await get_redis()
    for suffix in ("meta", "files"):
        await r.expire(_key(session_id, suffix), settings.SESSION_CACHE_TTL)


@_graceful()
async def delete_session(session_id: str) -> None:
    """Remove all Redis keys for a session."""
    r = await get_redis()
    for suffix in ("meta", "files"):
        await r.delete(_key(session_id, suffix))


@_graceful(default=False)
async def session_exists(session_id: str) -> bool:
    r = await get_redis()
    return bool(await r.exists(_key(session_id, "meta")))
