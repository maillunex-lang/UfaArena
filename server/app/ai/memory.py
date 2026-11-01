"""Long-term memory of AI personas (stage 14, decision D-06).

* Hot memory: `ai_memory` (facts, conversations, victories, defeats, decisions, promises, goals, relationships,
  personality changes) and `ai_activity_log` — kept for `hot_days` (90 by default) and used in behaviour and speech.
* Archive: older rows are summarised per persona and month into `ai_memory_archive` (counts per activity/kind and the
  important memories as text) and only then removed from the hot tables — history is never simply deleted.
* Biography: `ai_biographies` — structured chapters (created, guild, tier, personality, milestones), compacted when long.
* Checkpoints: `ai_persona_snapshots` — versioned personality snapshots; restore, export and import (profile transfer).
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..core.db import as_utc, utcnow
from ..models import AdminAction, AiActivityLog, AiBiography, AiMemory, AiMemoryArchive, AiPersona, AiPersonaSnapshot
from .sections import Section

KINDS = {"fact": "Факт", "conversation": "Разговор", "victory": "Победа", "defeat": "Поражение", "decision": "Решение",
         "promise": "Обещание", "goal": "Цель", "relationship": "Отношения", "personality": "Изменение характера",
         "event": "Событие мира", "habit": "Привычка"}
BIO_KINDS = {"created": "Начало пути", "guild": "Гильдия", "tier": "Новый уровень мастерства",
             "personality": "Характер", "milestone": "Достижение", "admin": "Правка администрации",
             "summary": "Ранние главы", "import": "Перенос профиля"}

SECTION = Section("ai_memory_settings",
                  {"hot_days": 90, "archive_batch": 400, "important_from": 2, "bio_max": 120, "snapshots_keep": 20,
                   "archive_every_min": 60},
                  {"hot_days": ("int", 7, 3650), "archive_batch": ("int", 50, 5000), "important_from": ("int", 1, 5),
                   "bio_max": ("int", 20, 1000), "snapshots_keep": ("int", 3, 200), "archive_every_min": ("int", 10, 1440)},
                  {"hot_days": "Горячая память, дней (потом — в архив)", "archive_batch": "Записей в архив за один проход",
                   "important_from": "Важность, с которой воспоминание сохраняется в архиве текстом",
                   "bio_max": "Глав биографии (старые сжимаются)", "snapshots_keep": "Контрольных точек на персонажа",
                   "archive_every_min": "Архивация каждые, минут"})

PERSONA_FIELDS = ("archetype", "style", "interests", "backstory", "temperament", "traits", "ambitions", "habits",
                  "voice", "mood", "tier", "pace", "personality_version")


# ------------------------------------------------------------------ hot memory
def add(db: Session, persona: AiPersona, kind: str, text: str, subject: str | None = None,
        importance: float = 1.0) -> AiMemory:
    m = AiMemory(persona_id=persona.id, subject_user_id=subject, fact=text[:200], kind=kind if kind in KINDS else "fact",
                 importance=float(max(0.0, min(5.0, importance))), created_at=utcnow())
    db.add(m)
    return m


def recall(db: Session, persona: AiPersona, subject: str | None = None, kinds: tuple | None = None,
           limit: int = 5) -> list[AiMemory]:
    q = select(AiMemory).where(AiMemory.persona_id == persona.id)
    if subject is not None:
        q = q.where(AiMemory.subject_user_id == subject)
    if kinds:
        q = q.where(AiMemory.kind.in_(kinds))
    return list(db.scalars(q.order_by(AiMemory.id.desc()).limit(max(1, limit))))


def search(db: Session, query: str = "", kind: str = "", persona_id: str = "", limit: int = 100) -> list[AiMemory]:
    q = select(AiMemory)
    if query:
        q = q.where(AiMemory.fact.ilike(f"%{query}%"))
    if kind:
        q = q.where(AiMemory.kind == kind)
    if persona_id:
        q = q.where(AiMemory.persona_id == persona_id)
    return list(db.scalars(q.order_by(AiMemory.id.desc()).limit(limit)))


# ------------------------------------------------------------------ biography
def bio(db: Session, persona: AiPersona) -> AiBiography:
    b = db.get(AiBiography, persona.id)
    if b is None:
        b = AiBiography(persona_id=persona.id, entries=[], updated_at=utcnow())
        db.add(b)
    return b


def bio_add(db: Session, persona: AiPersona, kind: str, text: str, limit: int | None = None) -> None:
    b = bio(db, persona)
    entries = list(b.entries or [])
    entries.append({"at": utcnow().isoformat(), "kind": kind, "text": text[:240]})
    limit = limit or 120
    if len(entries) > limit:  # compact the oldest chapters into one summary entry (size stays bounded)
        old, entries = entries[:len(entries) - limit + 1], entries[len(entries) - limit + 1:]
        counts = defaultdict(int)
        for e in old:
            counts[BIO_KINDS.get(e.get("kind"), e.get("kind"))] += 1
        first = old[0] if old[0].get("kind") != "summary" else None
        text0 = (old[0]["text"] + " ") if old[0].get("kind") == "summary" else ""
        summary = text0 + "; ".join(f"{k}: {v}" for k, v in counts.items() if k != BIO_KINDS["summary"])
        entries.insert(0, {"at": (first or old[0])["at"], "kind": "summary", "text": summary[:240]})
    b.entries, b.updated_at = entries, utcnow()


# ------------------------------------------------------------------ checkpoints, restore, transfer
def snapshot_data(persona: AiPersona) -> dict:
    return {k: getattr(persona, k) for k in PERSONA_FIELDS}


def checkpoint(db: Session, persona: AiPersona, reason: str, who: str = "system", keep: int | None = None) -> AiPersonaSnapshot:
    snap = AiPersonaSnapshot(persona_id=persona.id, version=persona.personality_version or 0, reason=reason[:160],
                             data=snapshot_data(persona), created_by=who[:64], created_at=utcnow())
    db.add(snap)
    db.flush()
    keep = keep or 20
    ids = list(db.scalars(select(AiPersonaSnapshot.id).where(AiPersonaSnapshot.persona_id == persona.id)
                          .order_by(AiPersonaSnapshot.id.desc())))
    first = ids[-1] if ids else None  # the very first snapshot (character at creation) is always kept
    for sid in ids[keep:]:
        if sid != first:
            db.delete(db.get(AiPersonaSnapshot, sid))
    return snap


def _apply(persona: AiPersona, data: dict) -> None:
    for k in PERSONA_FIELDS:
        if k in data and k != "personality_version":
            setattr(persona, k, data[k])


def restore(db: Session, persona: AiPersona, snap: AiPersonaSnapshot, who: str) -> None:
    checkpoint(db, persona, f"Перед восстановлением версии {snap.version}", who)
    _apply(persona, snap.data or {})
    persona.personality_version = (persona.personality_version or 0) + 1
    bio_add(db, persona, "admin", f"Характер восстановлен из контрольной точки от {as_utc(snap.created_at):%d.%m.%Y}")
    db.add(AdminAction(admin=who, action="ai_persona_restore", details={"persona": persona.id, "snapshot": snap.id}))


def export(db: Session, persona: AiPersona) -> dict:
    return {"format": "uralia-ai-persona/1", "exported_at": utcnow().isoformat(), "persona": snapshot_data(persona),
            "memories": [{"kind": m.kind, "text": m.fact, "importance": m.importance,
                          "at": as_utc(m.created_at).isoformat() if m.created_at else None}
                         for m in recall(db, persona, limit=500) if m.subject_user_id is None or m.kind != "conversation"],
            "biography": list(bio(db, persona).entries or []),
            "archive": [{"period": a.period, "stats": a.stats, "notes": a.notes} for a in
                        db.scalars(select(AiMemoryArchive).where(AiMemoryArchive.persona_id == persona.id))]}


def import_into(db: Session, persona: AiPersona, data: dict, who: str) -> None:
    """Profile transfer: personality, biography and general memories (memories about specific players are not moved —
    they belong to the original persona's relationships)."""
    if not isinstance(data, dict) or data.get("format") != "uralia-ai-persona/1":
        raise ValueError("Неверный формат файла персонажа")
    checkpoint(db, persona, "Перед импортом профиля", who)
    src = data.get("persona") or {}
    _apply(persona, {k: v for k, v in src.items() if k in PERSONA_FIELDS and k not in ("tier", "pace")})
    persona.personality_version = (persona.personality_version or 0) + 1
    for m in (data.get("memories") or [])[:200]:
        add(db, persona, str(m.get("kind", "fact")), str(m.get("text", ""))[:200], importance=float(m.get("importance", 1)))
    b = bio(db, persona)
    b.entries = (list(b.entries or []) + [e for e in (data.get("biography") or [])[-60:] if isinstance(e, dict)])[-120:]
    bio_add(db, persona, "import", "Перенесён профиль другого ИИ-персонажа")
    db.add(AdminAction(admin=who, action="ai_persona_import", details={"persona": persona.id}))


# ------------------------------------------------------------------ archive (never just delete)
def _archive_row(db: Session, cache: dict, persona_id: str, period: str) -> AiMemoryArchive:
    key = (persona_id, period)
    if key not in cache:
        row = db.scalar(select(AiMemoryArchive).where(AiMemoryArchive.persona_id == persona_id,
                                                      AiMemoryArchive.period == period))
        if row is None:
            row = AiMemoryArchive(persona_id=persona_id, period=period, stats={}, notes=[], updated_at=utcnow())
            db.add(row)
        cache[key] = row
    return cache[key]


def archive(db: Session, s: dict | None = None) -> dict:
    """Moves hot rows older than `hot_days` into the monthly archive in bounded batches. Each row is counted in the
    archive in the same transaction as it leaves the hot table, so nothing is lost or counted twice."""
    from datetime import timedelta
    s = s or SECTION.get(db)
    cutoff = utcnow() - timedelta(days=int(s["hot_days"]))
    batch = int(s["archive_batch"])
    cache: dict = {}
    moved_log = moved_mem = 0
    stats: dict = defaultdict(lambda: defaultdict(int))
    for a in db.scalars(select(AiActivityLog).where(AiActivityLog.created_at < cutoff).order_by(AiActivityLog.id).limit(batch)):
        stats[(a.persona_id, as_utc(a.created_at).strftime("%Y-%m"))]["act:" + a.activity] += 1
        db.delete(a)
        moved_log += 1
    notes: dict = defaultdict(list)
    old_mem = or_(AiMemory.created_at < cutoff, AiMemory.expires_at < utcnow())
    for m in db.scalars(select(AiMemory).where(old_mem).order_by(AiMemory.id).limit(batch)):
        at = as_utc(m.created_at or m.expires_at or utcnow())
        key = (m.persona_id, at.strftime("%Y-%m"))
        stats[key]["mem:" + (m.kind or "fact")] += 1
        if (m.importance or 1) >= s["important_from"]:
            notes[key].append({"kind": m.kind, "text": m.fact[:200], "at": at.isoformat()})
        db.delete(m)
        moved_mem += 1
    for key in set(stats) | set(notes):
        row = _archive_row(db, cache, *key)
        merged = dict(row.stats or {})
        for k, v in stats.get(key, {}).items():
            merged[k] = merged.get(k, 0) + v
        row.stats = merged
        row.notes = (list(row.notes or []) + notes.get(key, []))[-200:]
        row.updated_at = utcnow()
    db.flush()
    return {"activity": moved_log, "memories": moved_mem}
