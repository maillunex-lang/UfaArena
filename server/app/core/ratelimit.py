"""Fixed-window rate limiter. Uses Redis when configured, else in-process memory (single node dev)."""
from __future__ import annotations

import threading
import time

from fastapi import Request

from .config import get_settings
from .errors import GameError

_lock = threading.Lock()
_mem: dict[str, tuple[int, int]] = {}
_redis = None


def _client():
    global _redis
    url = get_settings().redis_url
    if not url:
        return None
    if _redis is None:
        import redis

        _redis = redis.Redis.from_url(url, socket_timeout=0.5)
    return _redis


def hit(key: str, limit: int, window_s: int = 60) -> None:
    window = int(time.time() // window_s)
    full = f"rl:{key}:{window}"
    r = _client()
    if r is not None:
        try:
            n = r.incr(full)
            if n == 1:
                r.expire(full, window_s + 1)
        except Exception:
            n = _mem_incr(full, window)
    else:
        n = _mem_incr(full, window)
    if n > limit:
        raise GameError("rate_limited", "Слишком много запросов, попробуйте позже", 429)


def _mem_incr(full: str, window: int) -> int:
    with _lock:
        if len(_mem) > 50_000:
            for k in [k for k, (w, _) in _mem.items() if w < window]:
                _mem.pop(k, None)
        w, n = _mem.get(full, (window, 0))
        n += 1
        _mem[full] = (window, n)
        return n


def reset() -> None:
    with _lock:
        _mem.clear()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
