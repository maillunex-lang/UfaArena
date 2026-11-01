"""AI Director task queue (spec §5). Every task: unique id, kind, persona, priority, creation time, run condition
(`run_after` + payload conditions), status, retry limit, result, error. Idempotency: a task is identified by `key`;
enqueuing the same key again is a no-op, and the action plus `status=done` are committed in one transaction."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.db import as_utc, utcnow
from ..models import AiTask, AiTaskHistory

LEASE_S = 120


def enqueue(db: Session, kind: str, key: str, persona_id: str | None = None, priority: int = 50,
            payload: dict | None = None, run_after=None, max_attempts: int = 3, status: str = "pending") -> AiTask | None:
    """Queue a task once. Returns None when a task with this key already exists (idempotent)."""
    if db.scalar(select(AiTask.id).where(AiTask.key == key)) is not None:
        return None
    t = AiTask(key=key[:128], kind=kind, persona_id=persona_id, priority=priority, payload=payload or {},
               run_after=run_after or utcnow(), max_attempts=max_attempts, status=status, attempts=0)
    try:
        with db.begin_nested():
            db.add(t)
            db.flush()
    except IntegrityError:  # a concurrent enqueue won the race
        return None
    return t


def claim(db: Session, limit: int) -> list[AiTask]:
    """Lease up to `limit` due tasks by priority (highest first), oldest first. Uses SKIP LOCKED on PostgreSQL."""
    now = utcnow()
    q = (select(AiTask).where(AiTask.status == "pending", AiTask.run_after <= now)
         .order_by(AiTask.priority.desc(), AiTask.id).limit(limit))
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)
    rows = list(db.scalars(q))
    for t in rows:
        t.status, t.lease_until, t.attempts = "running", now + timedelta(seconds=LEASE_S), (t.attempts or 0) + 1
    db.flush()
    return rows


def complete(t: AiTask, result: dict | None = None) -> None:
    t.status, t.result, t.error, t.finished_at, t.lease_until = "done", result or {}, None, utcnow(), None


def fail(t: AiTask, error: str) -> None:
    """Retry with backoff until max_attempts, then mark failed."""
    t.error = error[:300]
    t.lease_until = None
    if (t.attempts or 0) >= (t.max_attempts or 1):
        t.status, t.finished_at = "failed", utcnow()
    else:
        t.status = "pending"
        t.run_after = utcnow() + timedelta(seconds=15 * (2 ** max(0, (t.attempts or 1) - 1)))


def recover_stale(db: Session) -> int:
    """Tasks whose lease expired (process crashed mid-task) go back to the queue; their action had not committed."""
    now = utcnow()
    n = 0
    for t in db.scalars(select(AiTask).where(AiTask.status == "running", AiTask.lease_until < now)):
        fail(t, "lease expired (process restarted)")
        n += 1
    db.flush()
    return n


def compact(db: Session, older_than_hours: int) -> int:
    """Move finished tasks to ai_task_history so the hot queue stays small."""
    lim = utcnow() - timedelta(hours=older_than_hours)
    rows = list(db.scalars(select(AiTask).where(AiTask.status.in_(("done", "failed", "simulated", "cancelled")),
                                                AiTask.created_at < lim).limit(2000)))
    for t in rows:
        db.add(AiTaskHistory(task_id=t.id, kind=t.kind, persona_id=t.persona_id, status=t.status, attempts=t.attempts or 0,
                             result=t.result, error=t.error, created_at=as_utc(t.created_at), finished_at=t.finished_at))
        db.delete(t)
    db.flush()
    return len(rows)


def counts(db: Session) -> dict:
    from sqlalchemy import func
    return dict(db.execute(select(AiTask.status, func.count()).group_by(AiTask.status)).all())
