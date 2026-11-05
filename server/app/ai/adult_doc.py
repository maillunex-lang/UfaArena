"""18+ private-message templates uploaded by the admin as a text document.

Once a document is saved, it replaces the built-in flirt lines for adult DMs.
Minors never reach this code. Stop-phrases stay in adult.py and are not editable here.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ..models import ServerSetting

KEY = "ai_adult_dm_templates"
MAX_CHARS = 150_000
_BUNDLED = Path(__file__).with_name("adult_dm_default.txt")
_cache: dict = {"at": 0.0, "raw": None, "data": None}

SAMPLE = """# Шаблоны лички 18+. Строка с # — комментарий, бот её не читает.
# голос f — бот-девушка пишет игроку-мужчине
# голос m — бот-мужчина пишет игроку-женщине
# уровень 0 — лёгкий флирт, 1 — намёки, 2 — откровенно
# {имя} — ник игрока, {эхо} — 2–3 последних слова из его сообщения
# «если» — слова игрока через |. Пустое «если» — ответ на всё, что не попало в другие правила этого уровня.
# Несколько строк «- » — бот выбирает одну случайно.

голос: f
уровень: 0
первые:
- {имя}, привет. Заметила тебя и решила написать.
- Скучно одной. Составишь компанию?
если: привет | здравствуй | ку
ответы:
- Привет, {имя}. Рада, что написал.
- О, ты здесь. Как настроение?
если: скучаю | скучал | один
ответы:
- Я тоже. Расскажи, чем занят.
- Тогда я вовремя. Не пропадай.

голос: f
уровень: 1
если: обними | поцелуй | хочу тебя
ответы:
- «{эхо}»… мне это нравится. Продолжай.
- Если бы ты был рядом, я бы уже не отпускала.

голос: f
уровень: 2
если:
ответы:
- Напиши сюда свои фразы для откровенного уровня. Каждая с новой строки и дефиса.

голос: m
уровень: 0
первые:
- {имя}. Заметил тебя. Как дела?
если: привет | здравствуй
ответы:
- Привет. Давно хотел написать.
- Рад, что ты здесь.
уровень: 1
если: обними | поцелуй
ответы:
- Иди сюда. Я не из тех, кто только говорит.
уровень: 2
если:
ответы:
- Напиши сюда свои фразы для откровенного уровня. Каждая с новой строки и дефиса.
"""


def parse(text: str) -> dict:
    if not text or not text.strip():
        raise ValueError("Пустой документ")
    if len(text) > MAX_CHARS:
        raise ValueError("Документ больше 150 КБ")
    voice = None
    level = 0
    words: list[str] = []
    replies: list[str] = []
    blocks: list[dict] = []
    openers = {"f": [], "m": []}
    mode = None

    def flush() -> None:
        nonlocal replies, words
        if voice and replies:
            blocks.append({"voice": voice, "level": level, "words": list(words), "replies": list(replies)})
        replies = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        low = line.lower()
        if low.startswith("голос:"):
            flush()
            words = []
            v = low.split(":", 1)[1].strip()
            if v not in ("f", "m", "ж", "м"):
                raise ValueError(f"Неизвестный голос: {line}. Нужно f или m")
            voice = "f" if v in ("f", "ж") else "m"
            mode = None
            continue
        if low.startswith("уровень:"):
            flush()
            words = []
            try:
                level = int(low.split(":", 1)[1].strip())
            except ValueError as e:
                raise ValueError(f"Уровень должен быть 0, 1 или 2: {line}") from e
            if level not in (0, 1, 2):
                raise ValueError(f"Уровень должен быть 0, 1 или 2: {line}")
            mode = None
            continue
        if low.startswith("если:"):
            flush()
            words = [w.strip().lower() for w in low.split(":", 1)[1].split("|") if w.strip()]
            mode = None
            continue
        if low.startswith("первые:"):
            mode = "openers"
            continue
        if low.startswith("ответы:"):
            mode = "replies"
            continue
        item = line[2:].strip() if line.startswith("- ") else line[1:].strip() if line.startswith("-") else None
        if item is None:
            raise ValueError(f"Не понял строку (нужен «- текст» или слово раздела): {line[:80]}")
        if len(item) > 400:
            raise ValueError("Фраза длиннее 400 символов")
        if voice is None:
            raise ValueError("Сначала напишите строку «голос: f» или «голос: m»")
        if mode == "openers":
            openers[voice].append(item)
        elif mode == "replies":
            replies.append(item)
        else:
            raise ValueError(f"Фраза вне блока «ответы:» или «первые:»: {line[:80]}")
    flush()
    if not blocks and not any(openers.values()):
        raise ValueError("В документе нет ни одной фразы")
    return {"blocks": blocks, "openers": openers}


def _fill(line: str, name: str, echo: str) -> str:
    text = line.replace("{имя}", name or "").replace("{эхо}", echo or "")
    text = re.sub(r"\s{2,}", " ", text).strip(" ,")
    return text


def _echo(text: str) -> str:
    words = [w for w in re.findall(r"[А-Яа-яЁёA-Za-z0-9]{3,}", text or "") if w.lower() not in
             {"тебя", "тебе", "меня", "мне", "хочу", "очень", "просто", "такой", "такая", "этот", "это"}]
    return " ".join(words[-3:])[:40]


def _bundled() -> str:
    try:
        return _BUNDLED.read_text(encoding="utf-8")
    except OSError:
        return ""


def _source_text(db: Session) -> tuple[str, str]:
    """Admin upload wins. Otherwise the document shipped with the server."""
    row = db.get(ServerSetting, KEY)
    custom = (row.value or {}).get("text") if row is not None else None
    if custom:
        return custom, "admin"
    return _bundled(), "builtin"


def _word_in(text: str, word: str) -> bool:
    text = text.replace("ё", "е")
    word = word.replace("ё", "е")
    if len(word) <= 3:
        return re.search(rf"(?<![0-9a-zа-я]){re.escape(word)}(?![0-9a-zа-я])", text) is not None
    return word in text


def load(db: Session) -> dict | None:
    import time
    raw, _source = _source_text(db)
    if not raw:
        return None
    now = time.monotonic()
    if _cache["raw"] == raw and now - _cache["at"] < 30:
        return _cache["data"]
    try:
        data = parse(raw)
    except ValueError:
        return None
    _cache.update(at=now, raw=raw, data=data)
    return data


def active(db: Session) -> bool:
    return load(db) is not None


def status(db: Session) -> dict:
    raw, source = _source_text(db)
    if not raw:
        return {"loaded": False, "source": "", "sample": SAMPLE}
    data = load(db) or {"blocks": [], "openers": {"f": [], "m": []}}
    counts = {}
    for b in data["blocks"]:
        key = f"{b['voice']}:{b['level']}"
        counts[key] = counts.get(key, 0) + len(b["replies"])
    row = db.get(ServerSetting, KEY)
    return {"loaded": True, "source": source, "updated_at": (row.value or {}).get("updated_at") if row else None,
            "lines": sum(counts.values()) + sum(len(v) for v in data["openers"].values()),
            "rules": len(data["blocks"]), "by_level": counts,
            "openers": {k: len(v) for k, v in data["openers"].items()}, "sample": SAMPLE}


def save(db: Session, text: str, admin: str) -> dict:
    data = parse(text)
    row = db.get(ServerSetting, KEY)
    if row is None:
        row = ServerSetting(key=KEY, value={})
        db.add(row)
    row.value = {"text": text, "updated_at": datetime.utcnow().isoformat() + "Z", "admin": admin[:40]}
    _cache.update(at=0, raw=None, data=None)
    return {"rules": len(data["blocks"]), "openers": {k: len(v) for k, v in data["openers"].items()}}


def clear(db: Session) -> None:
    row = db.get(ServerSetting, KEY)
    if row is not None:
        row.value = {}
    _cache.update(at=0, raw=None, data=None)


def pick(db: Session, rng, voice: str, level: int, text: str, name: str = "") -> str | None:
    data = load(db)
    if not data:
        return None
    low = (text or "").lower().replace("ё", "е")
    best = 0
    chosen: list[dict] = []
    for block in data["blocks"]:
        if block["voice"] != voice or not block["words"]:
            continue
        hit = [w for w in block["words"] if _word_in(low, w)]
        if not hit:
            continue
        score = max(len(w) for w in hit)
        if score > best:
            best = score
            chosen = [block]
        elif score == best:
            chosen.append(block)
    if chosen:
        top = max(b["level"] for b in chosen)
        pool = [r for b in chosen if b["level"] == top for r in b["replies"]]
        if pool:
            return _fill(rng.choice(pool), name, _echo(text))
    for lv in (level, 1, 0):
        if lv > level:
            continue
        pool = [r for b in data["blocks"]
                if b["voice"] == voice and b["level"] == lv and not b["words"] for r in b["replies"]]
        if pool:
            return _fill(rng.choice(pool), name, _echo(text))
    return None


def opener(db: Session, rng, voice: str, name: str) -> str | None:
    data = load(db)
    if not data:
        return None
    pool = data["openers"].get(voice) or []
    if not pool:
        return None
    return _fill(rng.choice(pool), name, "")
