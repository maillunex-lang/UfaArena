"""Validated, versioned settings sections for the AI Control Center (speech, memory, tiers…): stored in
server_settings, every change logged to admin_actions with the previous version kept for rollback (spec §7, stage 18)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..models import AdminAction, ServerSetting


class Section:
    """fields: name -> ("int", lo, hi) | ("bool",) | ("choice", [values]) | ("str", max_len) | ("url", max_len)."""

    def __init__(self, key: str, defaults: dict, fields: dict, names: dict | None = None):
        self.key, self.defaults, self.fields, self.names = key, defaults, fields, names or {}

    def get(self, db: Session) -> dict:
        row = db.get(ServerSetting, self.key)
        stored = (row.value or {}) if row else {}
        return {**self.defaults, **{k: v for k, v in stored.items() if k in self.fields}}

    def validate(self, changes: dict) -> dict:
        out = {}
        for k, v in (changes or {}).items():
            f = self.fields.get(k)
            if f is None:
                raise ValueError(f"Неизвестный параметр: {k}")
            kind = f[0]
            if kind == "int":
                iv = int(v)
                if not f[1] <= iv <= f[2]:
                    raise ValueError(f"{self.names.get(k, k)}: допустимо {f[1]}…{f[2]}")
                out[k] = iv
            elif kind == "bool":
                if not isinstance(v, bool):
                    raise ValueError(f"{self.names.get(k, k)}: нужно да/нет")
                out[k] = v
            elif kind == "choice":
                if v not in f[1]:
                    raise ValueError(f"{self.names.get(k, k)}: одно из {', '.join(map(str, f[1]))}")
                out[k] = v
            elif kind in ("str", "url"):
                sv = str(v).strip()
                if len(sv) > f[1]:
                    raise ValueError(f"{self.names.get(k, k)}: не длиннее {f[1]} символов")
                if kind == "url" and sv and not sv.startswith(("http://", "https://")):
                    raise ValueError(f"{self.names.get(k, k)}: адрес должен начинаться с http:// или https://")
                out[k] = sv
        return out

    def update(self, db: Session, changes: dict, who: str) -> dict:
        clean = self.validate(changes)
        cur = self.get(db)
        hist = db.get(ServerSetting, self.key + "_history")
        if hist is None:
            hist = ServerSetting(key=self.key + "_history", value={"items": []})
            db.add(hist)
        hist.value = {"items": (list((hist.value or {}).get("items", [])) + [
            {"at": utcnow().isoformat(), "by": who, "settings": cur}])[-30:]}
        row = db.get(ServerSetting, self.key)
        if row is None:
            row = ServerSetting(key=self.key, value={})
            db.add(row)
        row.value = {**(row.value or {}), **clean}
        db.add(AdminAction(admin=who, action=self.key + "_settings", details=clean))
        db.flush()
        return self.get(db)

    def rollback(self, db: Session, who: str) -> dict:
        hist = db.get(ServerSetting, self.key + "_history")
        items = list((hist.value or {}).get("items", [])) if hist else []
        if not items:
            raise ValueError("Нет предыдущей версии настроек")
        prev = items.pop()
        hist.value = {"items": items}
        row = db.get(ServerSetting, self.key)
        if row is None:
            row = ServerSetting(key=self.key, value={})
            db.add(row)
        row.value = prev["settings"]
        db.add(AdminAction(admin=who, action=self.key + "_rollback", details={"to": prev["at"]}))
        db.flush()
        return self.get(db)

    def describe(self, db: Session) -> dict:
        return {"settings": self.get(db), "defaults": self.defaults, "names": self.names,
                "fields": {k: {"kind": v[0], "args": list(v[1]) if v[0] == "choice" else list(v[1:])}
                           for k, v in self.fields.items()}}
