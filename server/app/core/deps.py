from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import idempotency, ratelimit
from .config import get_settings
from .db import get_db
from .errors import GameError
from .security import CurrentUser, current_user


def player(request: Request, user: CurrentUser = Depends(current_user)) -> CurrentUser:
    """Authenticated + per-user rate limited."""
    ratelimit.hit(f"u:{user.id}", get_settings().rate_limit_per_minute)
    from ..social.anticheat import observe
    from ..social.common import touch
    touch(user.id)  # presence (throttled)
    observe(user.id)  # bot-like timing signal (flags only)
    return user


def run_idempotent(db: Session, user_id: str, key: str, endpoint: str, payload, fn: Callable[[], dict]) -> dict:
    cached = idempotency.lookup(db, user_id, key, endpoint, payload)
    if cached is not None:
        return {**cached, "replayed": True}
    try:
        resp = fn()
        idempotency.store(db, user_id, key, endpoint, payload, resp)
        db.commit()
    except IntegrityError:
        # concurrent duplicate request with the same key won the race
        db.rollback()
        cached = idempotency.lookup(db, user_id, key, endpoint, payload)
        if cached is None:
            raise GameError("conflict", "Конфликт параллельных запросов, повторите", 409)
        return {**cached, "replayed": True}
    except Exception:
        db.rollback()
        raise
    return resp


__all__ = ["player", "run_idempotent", "get_db", "CurrentUser"]
