"""Game -> AI event queue (spec §5.1 «получать события игры»). Replaces the in-process reply/mention queues of the v1
engine: events survive restarts and are visible to the separate Director process."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..models import AiEvent


def emit(db: Session, kind: str, payload: dict, persona_user_id: str | None = None, delay_s: float = 0.0) -> None:
    db.add(AiEvent(kind=kind, persona_user_id=persona_user_id, payload=payload,
                   due_at=utcnow() + timedelta(seconds=delay_s)))


def due(db: Session, limit: int, kinds: tuple[str, ...] | None = None) -> list[AiEvent]:
    q = select(AiEvent).where(AiEvent.handled_at.is_(None), AiEvent.due_at <= utcnow())
    if kinds:
        q = q.where(AiEvent.kind.in_(kinds))
    return list(db.scalars(q.order_by(AiEvent.id).limit(limit)))


def mark(ev: AiEvent) -> None:
    ev.handled_at = utcnow()


def prune(db: Session, days: int = 7) -> int:
    lim = utcnow() - timedelta(days=days)
    rows = list(db.scalars(select(AiEvent).where(AiEvent.handled_at.is_not(None), AiEvent.handled_at < lim).limit(5000)))
    for r in rows:
        db.delete(r)
    return len(rows)


def pending(db: Session) -> int:
    from sqlalchemy import func
    return db.scalar(select(func.count()).select_from(AiEvent).where(AiEvent.handled_at.is_(None))) or 0
