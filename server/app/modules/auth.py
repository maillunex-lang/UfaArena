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


class PasswordIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class RecoverIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=8, max_length=64)
    new_password: str = Field(min_length=8, max_length=128)


def _new_recovery_code(u: User) -> str:
    """One-time code shown to the player once; only its scrypt hash is stored."""
    import secrets
    raw = secrets.token_hex(6).upper()  # 12 hex chars
    code = "-".join(raw[i:i + 4] for i in range(0, 12, 4))
    u.recovery_hash = hash_password(code)
    return code


def _revoke_all(db: Session, user_id: str, keep: str | None = None) -> None:
    for s in db.scalars(select(SessionToken).where(SessionToken.user_id == user_id, SessionToken.revoked_at.is_(None))):
        if s.id != keep:
            s.revoked_at = utcnow()


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
    code = _new_recovery_code(u)
    audit(db, u.id, "auth.linked_email", ratelimit.client_ip(request))
    db.commit()
    return {"ok": True, "kind": u.kind, "recovery_code": code}


@router.post("/password")
def change_password(body: PasswordIn, request: Request, user: CurrentUser = Depends(current_user),
                    db: Session = Depends(get_db)):
    """Change the password; every other device is signed out."""
    _auth_limit(request)
    u = db.get(User, user.id)
    if not u.password_hash or not verify_password(body.old_password, u.password_hash):
        raise GameError("bad_credentials", "Текущий пароль неверен", 401)
    u.password_hash = hash_password(body.new_password)
    _revoke_all(db, u.id, keep=user.session_id)
    audit(db, u.id, "auth.password_changed", ratelimit.client_ip(request))
    db.commit()
    return {"ok": True}


@router.post("/recovery-code")
def recovery_code(request: Request, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    """Issue a new recovery code (the previous one stops working)."""
    _auth_limit(request)
    u = db.get(User, user.id)
    if not u.email:
        raise GameError("not_linked", "Сначала привяжите email", 409)
    code = _new_recovery_code(u)
    audit(db, u.id, "auth.recovery_code_issued", ratelimit.client_ip(request))
    db.commit()
    return {"recovery_code": code}


@router.post("/recover")
def recover(body: RecoverIn, request: Request, db: Session = Depends(get_db)):
    """Restore access with email + recovery code: sets a new password, signs out all devices,
    rotates the code (returned once) and signs in on this device."""
    _auth_limit(request)
    u = db.scalar(select(User).where(User.email == body.email.lower()))
    if u is None or not u.recovery_hash or not verify_password(body.code.strip().upper(), u.recovery_hash):
        raise GameError("bad_recovery", "Неверный email или код восстановления", 401)
    if u.is_banned:
        from ..social.moderation import ban_message
        raise GameError("banned", ban_message(db, u.id), 403)
    u.password_hash = hash_password(body.new_password)
    _revoke_all(db, u.id)
    code = _new_recovery_code(u)
    out = _issue(db, u, request)
    audit(db, u.id, "auth.recovered", ratelimit.client_ip(request))
    db.commit()
    return {**out, "recovery_code": code}


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
