"""Payments mode feature flag. TEST mode is the default and blocks every real charge.

Commercial mode can be enabled only by the owner, and only when ALL of these hold:
  1. env URALIA_PAYMENTS_COMMERCIAL_ALLOWED=1 on the server (deployment-level guard),
  2. a configured, verifiable provider (credentials present) — see payments.py,
  3. an explicit owner confirmation phrase passed to the admin CLI/API,
  4. the switch is audited (admin_actions) and can be reverted to test at any time.
"""
from __future__ import annotations

import os

from sqlalchemy.orm import Session

from ..models import AdminAction, ServerSetting

CONFIRM_PHRASE = "Я ВЛАДЕЛЕЦ И ВКЛЮЧАЮ РЕАЛЬНЫЕ ПЛАТЕЖИ"


class ModeError(ValueError):
    pass


def get_mode(db: Session) -> str:
    row = db.get(ServerSetting, "payments_mode")
    mode = (row.value or {}).get("mode", "test") if row else "test"
    # deployment guard: without the env flag the server behaves as TEST even if the DB says otherwise
    if mode == "commercial" and os.environ.get("URALIA_PAYMENTS_COMMERCIAL_ALLOWED") != "1":
        return "test"
    return mode


def is_test(db: Session) -> bool:
    return get_mode(db) != "commercial"


def set_mode(db: Session, mode: str, admin: str, confirm: str = "") -> str:
    from .payments import configured_providers

    if mode not in ("test", "commercial"):
        raise ModeError("mode must be test or commercial")
    if mode == "commercial":
        if os.environ.get("URALIA_PAYMENTS_COMMERCIAL_ALLOWED") != "1":
            raise ModeError("URALIA_PAYMENTS_COMMERCIAL_ALLOWED=1 is not set on the server")
        if confirm != CONFIRM_PHRASE:
            raise ModeError("owner confirmation phrase is required")
        if not configured_providers():
            raise ModeError("no payment provider is configured and verified")
    row = db.get(ServerSetting, "payments_mode")
    before = (row.value or {}).get("mode", "test") if row else "test"
    if row is None:
        row = ServerSetting(key="payments_mode", value={})
        db.add(row)
    row.value = {"mode": mode}
    db.add(AdminAction(admin=admin, action="payments.mode", details={"before": before, "after": mode}))
    db.commit()
    return mode
