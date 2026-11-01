"""Speech layer (stage 7): local templates and scenarios (dialogue.py, banter.py) + this layer that gives every persona
its own manner (voice), emotional colouring from mood, context from memory and the admin settings: intelligence,
message length, chat frequency, context depth and resource limits. An optional local open-source model (llm.py) can
write replies when it is enabled and the server has the resources; without it everything works on templates."""
from __future__ import annotations

import random
import re

from sqlalchemy.orm import Session

from ..models import AiPersona, PlayerProfile
from .sections import Section

SECTION = Section("ai_speech",
                  {"intelligence": 3, "length": "medium", "chat_frequency": 100, "context_depth": 5, "emotions": True,
                   "voice": True, "llm_enabled": False, "llm_url": "http://127.0.0.1:11434/v1", "llm_model": "qwen2.5:1.5b",
                   "llm_timeout_s": 4, "llm_max_per_hour": 30, "llm_min_free_mb": 8192, "llm_max_tokens": 80,
                   "chat_min_gap_s": 10, "chat_pause_min": 5, "chat_pause_max": 15},
                  {"intelligence": ("int", 1, 5), "length": ("choice", ["short", "medium", "long"]),
                   "chat_frequency": ("int", 0, 300), "context_depth": ("int", 0, 20), "emotions": ("bool",),
                   "voice": ("bool",), "llm_enabled": ("bool",), "llm_url": ("url", 200), "llm_model": ("str", 80),
                   "llm_timeout_s": ("int", 1, 30), "llm_max_per_hour": ("int", 0, 2000), "llm_min_free_mb": ("int", 512, 262144),
                   "llm_max_tokens": ("int", 16, 400), "chat_min_gap_s": ("int", 3, 600),
                   "chat_pause_min": ("int", 0, 240), "chat_pause_max": ("int", 0, 480)},
                  {"intelligence": "Интеллект (1 — просто шаблоны, 5 — память, контекст и локальная модель)",
                   "length": "Длина сообщений", "chat_frequency": "Частота общения, % от обычной",
                   "context_depth": "Глубина контекста (сколько воспоминаний учитывать)", "emotions": "Эмоциональные реакции",
                   "voice": "Индивидуальная манера речи", "llm_enabled": "Локальная языковая модель (необязательно)",
                   "llm_url": "Адрес локальной модели (OpenAI-совместимый: llama.cpp / Ollama)", "llm_model": "Модель",
                   "llm_timeout_s": "Ожидание ответа модели, секунд", "llm_max_per_hour": "Запросов к модели в час, максимум",
                   "llm_min_free_mb": "Минимум свободной памяти сервера для модели, МБ", "llm_max_tokens": "Длина ответа модели, токенов",
                   "chat_min_gap_s": "Пауза между сообщениями ИИ в одном канале, секунд (минимум)",
                   "chat_pause_min": "Тишина после обсуждения: от, минут", "chat_pause_max": "Тишина после обсуждения: до, минут"})

LENGTH_NAMES = {"short": "короткие", "medium": "обычные", "long": "развёрнутые"}
HAPPY = ["Ха, ", "Ура, ", "Эх, хорошо! ", "Настроение огонь — ", "Йес! "]
UPSET = ["Эх… ", "Ну такое. ", "Сегодня не мой день. ", "Хмф. ", "Ладно… "]
PROMISES = ["Как обещал — помогу, если позовёшь.", "Обещаю завтра зайти на босса.", "Если что — пиши, отвечу."]


def emotion(persona: AiPersona) -> str:
    m = persona.mood or 0.0
    return "happy" if m > 0.45 else "upset" if m < -0.45 else "calm"


def _first_sentence(text: str) -> str:
    m = re.match(r"(.+?[.!?…])(\s|$)", text)
    return m.group(1) if m else text


def stylize(rng: random.Random, persona: AiPersona, text: str, s: dict, extra: str = "") -> str:
    """Applies the persona's voice, mood and the length setting. Never longer than 300 characters."""
    out = text.strip()
    if s.get("length") == "short":
        out = _first_sentence(out)
    elif s.get("length") == "long" and extra:
        out = f"{out} {extra}"
    if s.get("emotions", True):
        e = emotion(persona)
        if e == "happy" and rng.random() < 0.35:
            out = rng.choice(HAPPY) + out[:1].lower() + out[1:]
        elif e == "upset" and rng.random() < 0.35:
            out = rng.choice(UPSET) + out
    v = persona.voice or {}
    if s.get("voice", True) and v:
        if v.get("catchphrase") and rng.random() < 0.15:
            out = f"{out.rstrip('.')} — {v['catchphrase']}." if rng.random() < 0.5 else f"{v['catchphrase'].capitalize()}, {out[:1].lower()}{out[1:]}"
        if v.get("exclaim", 0) > rng.random() and out.endswith("."):
            out = out[:-1] + "!"
        if v.get("ellipsis") and rng.random() < 0.3 and out.endswith((".", "!")):
            out = out[:-1] + "…"
        if v.get("emoji", 0) > rng.random() and v.get("emoji_set") and not re.search(r"[\U0001F300-\U0001FAFF]", out):
            out = f"{out} {rng.choice(v['emoji_set'])}"
        if v.get("lowercase") and rng.random() < 0.6:
            out = out[:1].lower() + out[1:]
    return out[:300]


def context_line(db: Session, rng: random.Random, persona: AiPersona, to_user: str | None, s: dict) -> str:
    """With higher intelligence a persona refers to what it remembers about the player and its own recent life."""
    from . import memory as MEM
    depth = int(s.get("context_depth", 5))
    if depth <= 0 or int(s.get("intelligence", 3)) < 2:
        return ""
    if to_user:
        mem = MEM.recall(db, persona, subject=to_user, limit=depth)
        prof = db.get(PlayerProfile, to_user)
        if mem and int(s["intelligence"]) >= 3:
            facts = [m for m in mem if m.kind in ("relationship", "promise", "victory", "defeat")]
            if facts:
                f = facts[0]
                if f.kind == "promise":
                    return rng.choice(PROMISES)
                if f.kind == "defeat":
                    return f"Кстати, {prof.nickname if prof else 'ты'}, я ещё помню нашу арену — реванш за мной 😏"
                if f.kind == "victory":
                    return "Помню, как мы встретились на арене. Без обид 🙂"
                return "Рад, что мы снова на связи."
            return "Помню, мы уже болтали."
    if int(s["intelligence"]) >= 4:
        own = MEM.recall(db, persona, kinds=("victory", "defeat", "personality"), limit=min(depth, 3))
        if own:
            m = own[0]
            return {"victory": "Я вот сегодня на арене выиграл.", "defeat": "Мне сегодня на арене не везёт.",
                    "personality": "Что-то я в последнее время изменился, сам замечаю."}.get(m.kind, "")
    return ""


def compose(db: Session, rng: random.Random, persona: AiPersona, base: str, to_user: str | None = None,
            user_text: str | None = None, kind: str = "") -> tuple[str, str]:
    """Final text of a persona's message. Returns (text, source) where source is "template" or "llm"."""
    s = SECTION.get(db)
    if user_text and kind not in ("who",) and int(s["intelligence"]) >= 5 and s.get("llm_enabled"):
        from . import llm
        reply = llm.reply(db, persona, user_text, s, context=context_line(db, rng, persona, to_user, s))
        if reply:
            return reply, "llm"
    extra = context_line(db, rng, persona, to_user, s) if int(s["intelligence"]) >= 3 else ""
    text = base
    if extra and s.get("length") != "short" and (s.get("length") == "long" or rng.random() < 0.4):
        text = f"{base} {extra}"
        extra = ""
    return stylize(rng, persona, text, s, extra), "template"


def frequency(db: Session) -> float:
    return max(0.0, SECTION.get(db)["chat_frequency"] / 100.0)
