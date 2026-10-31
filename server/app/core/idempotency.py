"""Idempotency for state-changing requests.

The client sends `Idempotency-Key`. The first successful response is stored in the
same transaction as the side effects; retries with the same key return the stored
response and never re-apply rewards. Same key + different payload -> 409.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import Header
from sqlalchemy.orm import Session

from ..models import IdempotencyKey
from .errors import GameError


def require_key(idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> str:
    if not idempotency_key or not (8 <= len(idempotency_key) <= 64):
        raise GameError("idempotency_key_required", "Нужен заголовок Idempotency-Key (8-64 символа)", 400)
    return idempotency_key


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def lookup(db: Session, user_id: str, key: str, endpoint: str, payload: Any) -> dict | None:
    row = db.get(IdempotencyKey, (user_id, key))
    if row is None:
        return None
    if row.endpoint != endpoint or row.request_hash != _hash(payload):
        raise GameError("idempotency_conflict", "Ключ уже использован для другого запроса", 409)
    return row.response


def store(db: Session, user_id: str, key: str, endpoint: str, payload: Any, response: dict) -> None:
    db.add(IdempotencyKey(user_id=user_id, key=key, endpoint=endpoint, request_hash=_hash(payload), response=response))
