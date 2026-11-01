"""AI Director settings and feature flags (Living World AI, stages 17/19/20). Stored in server_settings so the admin
panel changes them without restarts; every change keeps the previous version for rollback."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..models import AdminAction, ServerSetting

KEY = "ai_director"
HISTORY_KEY = "ai_director_history"
STATUS_KEY = "ai_director_status"

MODES = {
    "off": "Выключен — работает прежний движок ИИ (v1)",
    "test": "Тестовый — Director только планирует и журналирует, мир не меняется",
    "normal": "Обычный",
    "high": "Повышенная активность",
    "low": "Низкая нагрузка",
}
DEFAULTS = {
    "mode": "test",               # decision D-10: deploy in test mode
    "tick_seconds": 5,
    "max_tasks_per_tick": 8,      # upper bound; the adaptive budget moves below it (tuned to the 1-vCPU VPS audit)
    "tick_budget_ms": 1500,       # if a tick takes longer, the budget shrinks
    "registered_target": 500,     # decision D-07
    "active_min": 30,
    "active_max": 100,            # VPS audit: 1 vCPU / 2 GB shared with other projects
    # host load guard: load average per CPU in percent, available memory in MB
    "host_load_soft": 70,
    "host_load_hard": 150,
    "host_mem_soft_mb": 400,
    "host_mem_hard_mb": 200,
    # sleep when no real player is online: AI rest and cost nothing; the first real player wakes them up
    "sleep_when_empty": 1,
    "wake_grace_min": 10,
    # phase 4: social life (outreach to players, guild AI, groups)
    "social_life": 1,
    "outreach_every_s": 60,
    "guilds_every_s": 600,
    "groups_every_s": 900,
    "activities_every_s": 3600,
    "spawn_per_run": 20,          # new personas per population run (gradual growth)
    "population_every_s": 600,
    "compact_after_hours": 24,
    "events_per_tick": 10,
}
LIMITS = {"tick_seconds": (2, 120), "max_tasks_per_tick": (1, 200), "tick_budget_ms": (200, 20000),
          "registered_target": (0, 5000), "active_min": (0, 2000), "active_max": (0, 5000), "spawn_per_run": (0, 200),
          "population_every_s": (60, 86400), "compact_after_hours": (1, 24 * 30), "events_per_tick": (1, 200),
          "host_load_soft": (10, 1000), "host_load_hard": (10, 2000), "host_mem_soft_mb": (0, 65536),
          "host_mem_hard_mb": (0, 65536), "sleep_when_empty": (0, 1), "wake_grace_min": (0, 240),
          "social_life": (0, 1), "outreach_every_s": (15, 3600), "guilds_every_s": (60, 86400), "groups_every_s": (60, 86400),
          "activities_every_s": (300, 86400)}
# mode multipliers for activity (stage 19 modes)
MODE_FACTOR = {"normal": 1.0, "high": 1.6, "low": 0.4, "test": 1.0, "off": 0.0}


def get(db: Session) -> dict:
    row = db.get(ServerSetting, KEY)
    return {**DEFAULTS, **((row.value or {}) if row else {})}


def validate(changes: dict) -> dict:
    out = {}
    for k, v in changes.items():
        if k == "mode":
            if v not in MODES:
                raise ValueError(f"Неизвестный режим: {v}")
            out[k] = v
        elif k in LIMITS:
            lo, hi = LIMITS[k]
            iv = int(v)
            if not lo <= iv <= hi:
                raise ValueError(f"{k}: допустимо {lo}…{hi}")
            out[k] = iv
        else:
            raise ValueError(f"Неизвестный параметр: {k}")
    return out


def update(db: Session, changes: dict, who: str) -> dict:
    """Validated change; the previous settings are pushed to the history (last 30) for rollback; logged."""
    clean = validate(changes)
    cur = get(db)
    hist = db.get(ServerSetting, HISTORY_KEY)
    if hist is None:
        hist = ServerSetting(key=HISTORY_KEY, value={"items": []})
        db.add(hist)
    items = list((hist.value or {}).get("items", []))
    items.append({"at": utcnow().isoformat(), "by": who, "settings": cur})
    hist.value = {"items": items[-30:]}
    row = db.get(ServerSetting, KEY)
    if row is None:
        row = ServerSetting(key=KEY, value={})
        db.add(row)
    row.value = {**(row.value or {}), **clean}
    db.add(AdminAction(admin=who, action="ai_director_settings", details=clean))
    db.flush()
    return get(db)


def rollback(db: Session, who: str) -> dict:
    hist = db.get(ServerSetting, HISTORY_KEY)
    items = list((hist.value or {}).get("items", [])) if hist else []
    if not items:
        raise ValueError("Нет предыдущей версии настроек")
    prev = items.pop()
    hist.value = {"items": items}
    row = db.get(ServerSetting, KEY)
    if row is None:
        row = ServerSetting(key=KEY, value={})
        db.add(row)
    row.value = prev["settings"]
    db.add(AdminAction(admin=who, action="ai_director_rollback", details={"to": prev["at"]}))
    db.flush()
    return get(db)


def status(db: Session) -> dict:
    row = db.get(ServerSetting, STATUS_KEY)
    return dict(row.value or {}) if row else {}


def write_status(db: Session, data: dict) -> None:
    row = db.get(ServerSetting, STATUS_KEY)
    if row is None:
        row = ServerSetting(key=STATUS_KEY, value={})
        db.add(row)
    row.value = data


def director_owns_world(db: Session, max_age_s: int = 120) -> bool:
    """True when the Director is in an acting mode and alive (fresh heartbeat). Otherwise the legacy v1 engine in the
    API scheduler keeps the world running — so a crashed Director never freezes the AI population."""
    from datetime import datetime
    s = get(db)
    if s["mode"] not in ("normal", "high", "low"):
        return False
    hb = status(db).get("heartbeat")
    if not hb:
        return False
    try:
        age = (utcnow() - datetime.fromisoformat(hb)).total_seconds()
    except ValueError:
        return False
    return age <= max_age_s


def world_awake(db: Session, s: dict | None = None) -> bool:
    """False while no real player has been online for `wake_grace_min` minutes (when sleeping is enabled).
    A real player counts as online for 3 minutes after the last request (presence is updated once a minute)."""
    from datetime import timedelta
    from sqlalchemy import func, select
    from ..models import PlayerProfile
    s = s or get(db)
    if not int(s.get("sleep_when_empty", 1)):
        return True
    since = utcnow() - timedelta(minutes=3 + int(s.get("wake_grace_min", 10)))
    return (db.scalar(select(func.count()).select_from(PlayerProfile).where(
        PlayerProfile.is_ai.is_(False), PlayerProfile.last_seen_at >= since)) or 0) > 0
