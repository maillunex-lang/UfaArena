"""Moderation: reports, automatic short mutes, sanctions (warning / mute / temp ban / permanent ban),
appeals and violation history. Automatic actions are only short mutes; bans are always issued by a moderator."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import as_utc, get_db, utcnow
from ..core.deps import CurrentUser, player
from ..core.errors import GameError
from ..core.security import hash_token
from ..models import Appeal, ChatMessage, ChatReport, Sanction, SessionToken, SuspicionFlag, User
from .common import cfg, notify

router = APIRouter(prefix="/moderation", tags=["moderation"])

KIND_NAMES = {"warning": "Предупреждение", "mute": "Ограничение чата", "temp_ban": "Временная блокировка",
              "perm_ban": "Блокировка"}


def sanction_view(s: Sanction, appeal: Appeal | None = None) -> dict:
    return {"id": s.id, "kind": s.kind, "kind_name": KIND_NAMES.get(s.kind, s.kind), "reason": s.reason,
            "source": s.source, "status": s.status, "starts_at": as_utc(s.starts_at).isoformat(),
            "ends_at": as_utc(s.ends_at).isoformat() if s.ends_at else None,
            "appeal": {"status": appeal.status, "resolution": appeal.resolution} if appeal else None}


def issue(db: Session, user_id: str, kind: str, reason: str, minutes: int | None, by: str, source: str = "moderator") -> Sanction:
    if kind == "perm_ban" and source != "moderator":
        raise GameError("forbidden", "Бессрочная блокировка выдаётся только модератором", 403)
    s = Sanction(user_id=user_id, kind=kind, reason=reason[:300], source=source, created_by=by,
                 ends_at=(utcnow() + timedelta(minutes=minutes)) if minutes else None)
    db.add(s)
    if kind in ("temp_ban", "perm_ban"):
        u = db.get(User, user_id)
        if u is not None:
            u.is_banned = True
            for st in db.scalars(select(SessionToken).where(SessionToken.user_id == user_id, SessionToken.revoked_at.is_(None))):
                st.revoked_at = utcnow()
    if kind in ("mute", "temp_ban", "perm_ban"):  # hide recent messages of the offender from public channels
        since = utcnow() - timedelta(hours=1)
        for m in db.scalars(select(ChatMessage).where(ChatMessage.user_id == user_id, ChatMessage.created_at >= since)):
            if kind != "mute" or m.filtered:
                m.hidden = True
    db.flush()
    notify(db, user_id, KIND_NAMES.get(kind, kind),
           f"Причина: {reason}. " + (f"До {as_utc(s.ends_at).strftime('%d.%m.%Y %H:%M UTC')}." if s.ends_at else "")
           + " Вы можете подать апелляцию в разделе Профиль → Нарушения.", sender="Модерация")
    return s


def revoke(db: Session, s: Sanction, by: str) -> None:
    s.status = "revoked"
    if s.kind in ("temp_ban", "perm_ban"):
        still = db.scalar(select(func.count()).select_from(Sanction).where(
            Sanction.user_id == s.user_id, Sanction.status == "active", Sanction.id != s.id,
            Sanction.kind.in_(("temp_ban", "perm_ban")))) or 0
        if not still:
            u = db.get(User, s.user_id)
            if u:
                u.is_banned = False


def expire(db: Session) -> int:
    n = 0
    for s in db.scalars(select(Sanction).where(Sanction.status == "active", Sanction.ends_at.is_not(None),
                                               Sanction.ends_at <= utcnow())).all():
        s.status = "expired"
        if s.kind == "temp_ban":
            revoke(db, s, "system")
            s.status = "expired"
        n += 1
    db.flush()
    return n


def ban_message(db: Session, user_id: str) -> str:
    s = db.scalars(select(Sanction).where(Sanction.user_id == user_id, Sanction.status == "active",
                                          Sanction.kind.in_(("temp_ban", "perm_ban"))).order_by(Sanction.id.desc())).first()
    if s is None:
        return "Аккаунт заблокирован"
    until = as_utc(s.ends_at).strftime("%d.%m.%Y %H:%M UTC") if s.ends_at else "бессрочно"
    return f"Аккаунт заблокирован ({until}). Причина: {s.reason}. Номер санкции {s.id} — для апелляции."


def auto_review(db: Session, target: str) -> None:
    """N distinct reporters for abuse/spam within 24h => short automatic mute; reports stay open for a moderator."""
    c = cfg()["chat"]
    since = utcnow() - timedelta(hours=24)
    reporters = db.scalar(select(func.count(func.distinct(ChatReport.reporter_id))).where(
        ChatReport.target_id == target, ChatReport.status == "open", ChatReport.created_at >= since,
        ChatReport.reason.in_(("abuse", "spam", "scam")))) or 0
    if reporters >= c["auto_mute_reports"]:
        from .chat import active_sanction
        if active_sanction(db, target, ("mute",)) is None:
            issue(db, target, "mute", "Автоматически: несколько жалоб игроков (до проверки модератором)",
                  c["auto_mute_minutes"], "auto", source="auto")


# ------------------------------------------------------------------ player API
@router.get("/my")
def my(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    rows = db.scalars(select(Sanction).where(Sanction.user_id == user.id).order_by(Sanction.id.desc()).limit(30)).all()
    return {"sanctions": [sanction_view(s, db.scalar(select(Appeal).where(Appeal.sanction_id == s.id))) for s in rows]}


class AppealIn(BaseModel):
    sanction_id: int
    text: str = Field(min_length=10, max_length=1000)


def _appeal(db: Session, user_id: str, body: AppealIn) -> dict:
    s = db.get(Sanction, body.sanction_id)
    if s is None or s.user_id != user_id:
        raise GameError("not_found", "Санкция не найдена", 404)
    if db.scalar(select(Appeal).where(Appeal.sanction_id == s.id)):
        raise GameError("already", "Апелляция уже подана", 409)
    db.add(Appeal(sanction_id=s.id, user_id=user_id, text=body.text.strip()))
    db.commit()
    return {"ok": True}


@router.post("/appeal")
def appeal(body: AppealIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    return _appeal(db, user.id, body)


class BanAppealIn(AppealIn):
    refresh_token: str = Field(min_length=10, max_length=200)


@router.post("/ban-appeal")
def ban_appeal(body: BanAppealIn, db: Session = Depends(get_db)):
    """A banned player cannot log in; the stored refresh token proves account ownership for the appeal."""
    sess = db.scalar(select(SessionToken).where(SessionToken.refresh_hash == hash_token(body.refresh_token)))
    if sess is None:
        raise GameError("not_found", "Сессия не найдена", 404)
    return _appeal(db, sess.user_id, body)


_ = SuspicionFlag
