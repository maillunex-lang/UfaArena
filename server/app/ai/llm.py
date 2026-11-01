"""Optional local open-source language model adapter (stage 7, decision D-09).

* Off by default. Talks to a model running on the same server or local network through the OpenAI-compatible HTTP API
  that llama.cpp (`llama-server`) and Ollama provide — no paid external services, no internet needed.
* Used only when enabled, when the server has at least `llm_min_free_mb` of free memory and within the hourly limit.
* Any problem (not running, slow, odd answer) silently falls back to the template system, which always works.
* Answers are filtered: length limit, no links, never claims to be a human; the persona is always an AI character."""
from __future__ import annotations

import json
import time
import urllib.request

from sqlalchemy.orm import Session

from ..models import AiPersona, PlayerProfile
from . import hostload as HL

_calls: list[float] = []
_state: dict = {"last_error": None, "last_ok": None, "calls_hour": 0}
BAD = ("http://", "https://", "www.", "я человек", "я не бот", "я не ии", "я живой человек", "оплат", "купи ")


def availability(s: dict) -> tuple[bool, str]:
    if not s.get("llm_enabled"):
        return False, "Выключена в настройках"
    mem = HL.snapshot().get("mem_avail_mb")
    if mem is not None and mem < int(s["llm_min_free_mb"]):
        return False, f"Мало свободной памяти сервера: {mem} МБ < {s['llm_min_free_mb']} МБ"
    now = time.time()
    while _calls and _calls[0] < now - 3600:
        _calls.pop(0)
    _state["calls_hour"] = len(_calls)
    if len(_calls) >= int(s["llm_max_per_hour"]):
        return False, "Достигнут лимит запросов в час"
    return True, "Готова"


def status(s: dict) -> dict:
    ok, why = availability(s)
    return {"enabled": bool(s.get("llm_enabled")), "available": ok, "reason": why, **_state}


def _system_prompt(db: Session, persona: AiPersona) -> str:
    from .personality import TRAITS
    prof = db.get(PlayerProfile, persona.user_id)
    strong = [TRAITS[t].lower() for t, v in sorted((persona.traits or {}).items(), key=lambda kv: -kv[1])[:2] if t in TRAITS]
    return (f"Ты — ИИ-персонаж мобильной игры «Уралия» по имени {prof.nickname if prof else 'Путник'}. Ты не человек и "
            f"никогда не выдаёшь себя за человека; если спросят — честно скажи, что ты ИИ-житель игры. Черты: "
            f"{', '.join(strong)}. Стиль: {persona.style}. Отвечай по-русски, коротко (1–2 предложения), дружелюбно, по "
            f"теме игры (герои, арена, боссы, гильдии, события). Без ссылок, без советов покупать что-либо, без личных "
            f"данных.")


def reply(db: Session, persona: AiPersona, user_text: str, s: dict, context: str = "") -> str | None:
    ok, why = availability(s)
    if not ok:
        return None
    _calls.append(time.time())
    body = {"model": s["llm_model"], "max_tokens": int(s["llm_max_tokens"]), "temperature": 0.8,
            "messages": [{"role": "system", "content": _system_prompt(db, persona) + (f" Контекст: {context}" if context else "")},
                         {"role": "user", "content": user_text[:300]}]}
    req = urllib.request.Request(s["llm_url"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=int(s["llm_timeout_s"])) as r:  # noqa: S310 (admin-configured local URL)
            data = json.loads(r.read().decode("utf-8", "replace"))
        text = (data["choices"][0]["message"]["content"] or "").strip().replace("\n", " ")
    except Exception as e:  # not running, slow or malformed: templates take over
        _state["last_error"] = f"{type(e).__name__}: {str(e)[:120]}"
        return None
    low = text.lower()
    if not text or len(text) > 400 or any(b in low for b in BAD):
        _state["last_error"] = "Ответ отклонён фильтром"
        return None
    _state["last_ok"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return text[:300]
