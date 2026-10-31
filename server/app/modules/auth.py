from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import ratelimit
from ..core.audit import audit
from ..core.config import get_settings
from ..core.db import as_utc, get_db, utcnow
from ..core.errors import GameError
from ..core.security import (
    CurrentUser, create_access_token, current_user, hash_password, hash_token, new_refresh_token, verify_password,
)
from ..models import SessionToken, User
from ..services import create_player

router = APIRouter(prefix="/auth", tags=["auth"])


class GuestIn(BaseModel):
    device_id: str = Field(min_length=8, max_length=128)
    client_version: str = Field(default="0.0.0", max_length=16)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class LinkIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(LinkIn):
    pass


def _issue(db: Session, user: User, request: Request, family_id: str | None = None) -> dict:
    s = get_settings()
    token, token_hash = new_refresh_token()
    sess = SessionToken(user_id=user.id, family_id=family_id or "", refresh_hash=token_hash,
                        expires_at=utcnow() + timedelta(seconds=s.refresh_token_ttl_s),
                        user_agent=(request.headers.get("user-agent") or "")[:255])
    db.add(sess)
    db.flush()
    if not family_id:
        sess.family_id = sess.id
    return {"access_token": create_access_token(user.id, sess.id), "refresh_token": token,
            "token_type": "bearer", "expires_in": s.access_token_ttl_s, "user_id": user.id}


def _auth_limit(request: Request) -> None:
    ratelimit.hit(f"auth:{ratelimit.client_ip(request)}", get_settings().auth_rate_limit_per_minute)


@router.post("/guest")
def guest(body: GuestIn, request: Request, db: Session = Depends(get_db)):
    """Creates a NEW guest account. Returning players use /auth/refresh with their stored token."""
    _auth_limit(request)
    user = create_player(db, body.device_id)
    out = _issue(db, user, request)
    audit(db, user.id, "auth.guest_created", ratelimit.client_ip(request), client_version=body.client_version)
    db.commit()
    return out


@router.post("/refresh")
def refresh(body: RefreshIn, request: Request, db: Session = Depends(get_db)):
    _auth_limit(request)
    sess = db.scalar(select(SessionToken).where(SessionToken.refresh_hash == hash_token(body.refresh_token)))
    if sess is None:
        raise GameError("refresh_invalid", "Сессия не найдена", 401)
    if sess.revoked_at is not None or sess.rotated_at is not None:
        # Reuse of a rotated token => likely theft: revoke the whole family.
        for s in db.scalars(select(SessionToken).where(SessionToken.family_id == sess.family_id)):
            s.revoked_at = s.revoked_at or utcnow()
        audit(db, sess.user_id, "auth.refresh_reuse_detected", ratelimit.client_ip(request))
        db.commit()
        raise GameError("refresh_reused", "Сессия отозвана, войдите снова", 401)
    if as_utc(sess.expires_at) < utcnow():
        raise GameError("refresh_expired", "Сессия истекла", 401)
    user = db.get(User, sess.user_id)
    if user is None:
        raise GameError("forbidden", "Доступ запрещён", 403)
    if user.is_banned:
        from ..social.moderation import ban_message
        raise GameError("banned", ban_message(db, user.id), 403)
    sess.rotated_at = utcnow()
    out = _issue(db, user, request, family_id=sess.family_id)
    db.commit()
    return out


@router.post("/link")
def link(body: LinkIn, request: Request, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    """Attach email+password (URALIA ID) to the current guest account."""
    _auth_limit(request)
    u = db.get(User, user.id)
    if u.email:
        raise GameError("already_linked", "Аккаунт уже привязан")
    if db.scalar(select(User).where(User.email == body.email.lower())) is not None:
        raise GameError("email_taken", "Email уже используется", 409)
    u.email, u.password_hash, u.kind = body.email.lower(), hash_password(body.password), "linked"
    audit(db, u.id, "auth.linked_email", ratelimit.client_ip(request))
    db.commit()
    return {"ok": True, "kind": u.kind}


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    _auth_limit(request)
    u = db.scalar(select(User).where(User.email == body.email.lower()))
    if u is None or not u.password_hash or not verify_password(body.password, u.password_hash):
        raise GameError("bad_credentials", "Неверный email или пароль", 401)
    out = _issue(db, u, request)
    audit(db, u.id, "auth.login", ratelimit.client_ip(request))
    db.commit()
    return out


@router.post("/logout")
def logout(user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    sess = db.get(SessionToken, user.session_id)
    sess.revoked_at = utcnow()
    db.commit()
    return {"ok": True}
