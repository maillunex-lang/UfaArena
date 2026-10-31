"""Access tokens (short-lived JWT) + opaque rotating refresh tokens + password hashing."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import timedelta

import jwt
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db, utcnow
from .errors import GameError

ALG = "HS256"


def create_access_token(user_id: str, session_id: str) -> str:
    s = get_settings()
    now = utcnow()
    payload = {
        "sub": user_id,
        "sid": session_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=s.access_token_ttl_s)).timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=ALG)


def decode_access_token(token: str) -> dict:
    try:
        data = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALG])
    except jwt.ExpiredSignatureError:
        raise GameError("token_expired", "Срок действия токена истёк", 401)
    except jwt.PyJWTError:
        raise GameError("token_invalid", "Недействительный токен", 401)
    if data.get("typ") != "access":
        raise GameError("token_invalid", "Недействительный токен", 401)
    return data


def new_refresh_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# scrypt: stdlib, memory-hard. Format: scrypt$n$r$p$salt$hash
_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        _N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(dk).decode()
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt_b64, dk_b64 = stored.split("$")
        dk = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:
        return False


class CurrentUser:
    def __init__(self, user_id: str, session_id: str):
        self.id = user_id
        self.session_id = session_id


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> CurrentUser:
    from ..models import SessionToken, User

    if not authorization or not authorization.lower().startswith("bearer "):
        raise GameError("unauthorized", "Требуется авторизация", 401)
    data = decode_access_token(authorization.split(" ", 1)[1].strip())
    sess = db.get(SessionToken, data["sid"])
    if sess is None or sess.revoked_at is not None:
        raise GameError("session_revoked", "Сессия завершена", 401)
    user = db.get(User, data["sub"])
    if user is None or user.is_banned:
        raise GameError("forbidden", "Доступ запрещён", 403)
    return CurrentUser(user.id, sess.id)
