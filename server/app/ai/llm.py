"""Language model adapter for AI residents' replies (stage 7, decision D-09 amended by the owner on 2026-11-01).

Templates stay the foundation; a model only improves replies to real players and is OFF by default.
Providers (all speak the OpenAI-compatible chat API, chosen in the admin panel):
* local       — llama.cpp `llama-server` / Ollama on the own server or LAN; used only with enough free memory;
* groq        — Groq Cloud free tier;
* google      — Google AI Studio (Gemini) free tier, OpenAI-compatible endpoint;
* openrouter  — OpenRouter, free models with the `:free` suffix;
* cloudflare  — Cloudflare Workers AI (needs the account id);
* huggingface — Hugging Face Inference Providers router.

Keys live only on the server: environment variables (`URALIA_LLM_<PROVIDER>_KEY`) or entered in the admin panel
(stored in server_settings "ai_llm_keys", never returned in full, never written to logs, never sent to the client).
External providers receive no player identifiers: the player's nickname is replaced, only the message text and the AI
character description are sent. Any problem (no key, limit, region block, timeout, odd answer) -> templates."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from sqlalchemy.orm import Session

from ..models import AdminAction, AiPersona, PlayerProfile, ServerSetting
from . import hostload as HL

PROVIDERS = {
    "local": {"name": "Локальная модель (llama.cpp / Ollama на своём сервере)", "url": None,
              "model": "qwen2.5:1.5b", "external": False, "key": False,
              "hint": "Нужен запущенный llama-server или Ollama и ≥ 8 ГБ свободной памяти (на текущем VPS — нет)."},
    "groq": {"name": "Groq Cloud (бесплатный тариф)", "url": "https://api.groq.com/openai/v1",
             "model": "llama-3.3-70b-versatile", "external": True, "key": True,
             "hint": "Ключ: console.groq.com → API Keys. Очень быстрый."},
    "google": {"name": "Google AI Studio — Gemini (бесплатный тариф)",
               "url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.0-flash",
               "external": True, "key": True,
               "hint": "Ключ: aistudio.google.com → Get API key. Лучший русский; возможны ограничения по региону; на бесплатном тарифе данные могут использоваться для обучения."},
    "openrouter": {"name": "OpenRouter (бесплатные модели :free)", "url": "https://openrouter.ai/api/v1",
                   "model": "meta-llama/llama-3.3-70b-instruct:free", "external": True, "key": True,
                   "hint": "Ключ: openrouter.ai → Keys. Модели с суффиксом :free бесплатны, бывают перегружены."},
    "cloudflare": {"name": "Cloudflare Workers AI", "url": "https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1",
                   "model": "@cf/meta/llama-3.1-8b-instruct", "external": True, "key": True,
                   "hint": "Токен: dash.cloudflare.com → My Profile → API Tokens (Workers AI). Нужен ещё ID аккаунта."},
    "huggingface": {"name": "Hugging Face Inference", "url": "https://router.huggingface.co/v1",
                    "model": "meta-llama/Llama-3.1-8B-Instruct", "external": True, "key": True,
                    "hint": "Токен: huggingface.co → Settings → Access Tokens. Первый ответ может быть медленным."},
}
KEYS_KEY = "ai_llm_keys"

_calls: list[float] = []
_state: dict = {"last_error": None, "last_ok": None, "calls_hour": 0, "last_latency_ms": None}
BAD = ("http://", "https://", "www.", "я человек", "я не бот", "я не ии", "я живой человек", "оплат", "купи ", "задонать")


# ------------------------------------------------------------------ keys (server-only secrets)
def _stored_keys(db: Session) -> dict:
    row = db.get(ServerSetting, KEYS_KEY)
    return dict(row.value or {}) if row else {}


def key_for(db: Session, provider: str) -> str:
    env = os.environ.get(f"URALIA_LLM_{provider.upper()}_KEY", "").strip()
    return env or str(_stored_keys(db).get(provider, "")).strip()


def account_for(db: Session, s: dict) -> str:
    return os.environ.get("URALIA_LLM_CLOUDFLARE_ACCOUNT", "").strip() or str(s.get("llm_cloudflare_account", "")).strip()


def set_key(db: Session, provider: str, key: str, who: str) -> None:
    if provider not in PROVIDERS or not PROVIDERS[provider]["key"]:
        raise ValueError("Для этого поставщика ключ не нужен")
    key = (key or "").strip()
    if len(key) > 300 or any(c.isspace() for c in key):
        raise ValueError("Ключ выглядит неверно")
    row = db.get(ServerSetting, KEYS_KEY)
    if row is None:
        row = ServerSetting(key=KEYS_KEY, value={})
        db.add(row)
    vals = dict(row.value or {})
    if key:
        vals[provider] = key
    else:
        vals.pop(provider, None)
    row.value = vals
    db.add(AdminAction(admin=who, action="ai_llm_key", details={"provider": provider, "set": bool(key)}))  # no value


def masked_keys(db: Session) -> dict:
    out = {}
    for p, meta in PROVIDERS.items():
        if not meta["key"]:
            continue
        env = bool(os.environ.get(f"URALIA_LLM_{p.upper()}_KEY", "").strip())
        k = key_for(db, p)
        out[p] = {"configured": bool(k), "source": "env" if env else ("admin" if k else None),
                  "mask": ("••••" + k[-4:]) if len(k) >= 8 else ("••••" if k else "")}
    return out


# ------------------------------------------------------------------ endpoint resolution and availability
def endpoint(db: Session, s: dict) -> tuple[str, str, str]:
    """(base_url, model, key) for the selected provider."""
    p = s.get("llm_provider", "local")
    meta = PROVIDERS.get(p, PROVIDERS["local"])
    if p == "local":
        url = s.get("llm_url") or "http://127.0.0.1:11434/v1"
    else:
        url = meta["url"].replace("{account}", account_for(db, s) or "ACCOUNT_ID")
    model = (s.get("llm_model") or "").strip() or meta["model"]
    return url, model, key_for(db, p) if meta["key"] else ""


def availability(s: dict, db: Session | None = None, count_limit: bool = True) -> tuple[bool, str]:
    if not s.get("llm_enabled"):
        return False, "Выключена в настройках"
    p = s.get("llm_provider", "local")
    meta = PROVIDERS.get(p)
    if meta is None:
        return False, "Неизвестный поставщик"
    if p == "local":
        mem = HL.snapshot().get("mem_avail_mb")
        if mem is not None and mem < int(s["llm_min_free_mb"]):
            return False, f"Мало свободной памяти сервера для локальной модели: {mem} МБ < {s['llm_min_free_mb']} МБ"
    elif db is not None:
        if not key_for(db, p):
            return False, "Не указан ключ API для «" + meta["name"].split(" (")[0] + "»"
        if p == "cloudflare" and not account_for(db, s):
            return False, "Не указан ID аккаунта Cloudflare"
    if count_limit:
        now = time.time()
        while _calls and _calls[0] < now - 3600:
            _calls.pop(0)
        _state["calls_hour"] = len(_calls)
        if len(_calls) >= int(s["llm_max_per_hour"]):
            return False, "Достигнут лимит запросов в час"
    return True, "Готова"


def status(s: dict, db: Session | None = None) -> dict:
    ok, why = availability(s, db)
    p = s.get("llm_provider", "local")
    return {"enabled": bool(s.get("llm_enabled")), "available": ok, "reason": why, "provider": p,
            "provider_name": PROVIDERS.get(p, {}).get("name"), "external": PROVIDERS.get(p, {}).get("external", False),
            **_state}


# ------------------------------------------------------------------ request
def _system_prompt(db: Session, persona: AiPersona) -> str:
    from .personality import TRAITS
    prof = db.get(PlayerProfile, persona.user_id)
    strong = [TRAITS[t].lower() for t, v in sorted((persona.traits or {}).items(), key=lambda kv: -kv[1])[:2] if t in TRAITS]
    return (f"Ты — ИИ-персонаж мобильной игры «Уралия» по имени {prof.nickname if prof else 'Путник'}. Ты не человек и "
            f"никогда не выдаёшь себя за человека; если спросят — честно скажи, что ты ИИ-житель игры. Черты: "
            f"{', '.join(strong)}. Стиль: {persona.style}. Отвечай по-русски, коротко (1–2 предложения), дружелюбно, по "
            f"теме игры (герои, арена, боссы, гильдии, события, сюжет об Урал-батыре). Без ссылок, без советов покупать "
            f"что-либо, не проси и не называй личные данные.")


def _call(url: str, model: str, key: str, system: str, user_text: str, s: dict) -> tuple[str | None, str | None, int]:
    body = {"model": model, "max_tokens": int(s["llm_max_tokens"]), "temperature": 0.8,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user_text[:300]}]}
    headers = {"Content-Type": "application/json", "User-Agent": "uralia-server/1"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if "openrouter.ai" in url:
        headers["X-Title"] = "Uralia"
    req = urllib.request.Request(url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers=headers, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=int(s["llm_timeout_s"])) as r:  # noqa: S310 (admin-chosen endpoint)
            data = json.loads(r.read().decode("utf-8", "replace"))
        text = (data["choices"][0]["message"]["content"] or "").strip().replace("\n", " ")
        return text, None, int((time.perf_counter() - t0) * 1000)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:160]
        except Exception:
            pass
        hint = {401: "неверный ключ", 403: "доступ запрещён (ключ или регион)", 404: "нет такой модели или адреса",
                429: "превышен лимит бесплатного тарифа"}.get(e.code, "")
        return None, f"HTTP {e.code} {hint} {detail}".strip(), int((time.perf_counter() - t0) * 1000)
    except Exception as e:  # not running, slow, region block, malformed
        return None, f"{type(e).__name__}: {str(e)[:140]}", int((time.perf_counter() - t0) * 1000)


def _clean(text: str | None) -> tuple[str | None, str | None]:
    if not text:
        return None, "Пустой ответ"
    low = text.lower()
    if len(text) > 400 or any(b in low for b in BAD):
        return None, "Ответ отклонён фильтром"
    return text[:300], None


def reply(db: Session, persona: AiPersona, user_text: str, s: dict, context: str = "", to_user: str | None = None) -> str | None:
    ok, why = availability(s, db)
    if not ok:
        return None
    url, model, key = endpoint(db, s)
    external = PROVIDERS.get(s.get("llm_provider", "local"), {}).get("external", False)
    if external and to_user:  # no player identifiers leave the server
        tp = db.get(PlayerProfile, to_user)
        if tp and tp.nickname:
            user_text = user_text.replace(tp.nickname, "собеседник")
            context = context.replace(tp.nickname, "собеседник")
    _calls.append(time.time())
    text, err, ms = _call(url, model, key, _system_prompt(db, persona) + (f" Контекст: {context}" if context else ""),
                          user_text, s)
    _state["last_latency_ms"] = ms
    if err:
        _state["last_error"] = err
        return None
    text, err = _clean(text)
    if err:
        _state["last_error"] = err
        return None
    _state["last_ok"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return text


def test(db: Session, s: dict, provider: str | None = None) -> dict:
    """Admin "check connection": one request with a sample question (counts towards the hourly limit)."""
    s = {**s, "llm_enabled": True, **({"llm_provider": provider} if provider else {})}
    if provider and provider != s.get("llm_provider"):
        s["llm_model"] = ""
    ok, why = availability(s, db)
    if not ok:
        return {"ok": False, "error": why}
    url, model, key = endpoint(db, s)
    _calls.append(time.time())
    system = ("Ты — ИИ-персонаж мобильной игры «Уралия». Ты не человек. Отвечай по-русски, коротко (1–2 предложения).")
    text, err, ms = _call(url, model, key, system, "Привет! Что посоветуешь новичку на арене?", s)
    if not err:
        text, err = _clean(text)
    _state["last_latency_ms"] = ms
    if err:
        _state["last_error"] = err
    else:
        _state["last_ok"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return {"ok": not err, "text": text, "error": err, "latency_ms": ms, "model": model,
            "endpoint": url.split("/accounts/")[0] if "cloudflare" in url else url}
