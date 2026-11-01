"""Replaceable game art: catalog of slots (with advice and prompts), staging uploads and publishing them to
players as a content package (no new APK). The client looks up every slot at `art/<path>` in mounted
content and falls back to the built-in art when the slot is empty."""
from __future__ import annotations

import json
import struct
from pathlib import Path

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import utcnow
from ..game import data as D

STYLE = ("dark fantasy mobile game art, Ural mountains and Bashkir ornament motifs, deep graphite and dark teal, "
         "polished gold accents, premium, high detail, no text, no watermark")
MAX_BYTES = 8 * 1024 * 1024
PACKAGE_ID = "ui.art"

ICON_KINDS = {
    "gold": "Золото", "crystals": "Кристаллы", "summon_essence": "Эссенция призыва", "nature_essence": "Эссенция природы",
    "ancient_seals": "Древние печати", "guild_marks": "Знаки гильдии", "friend_tokens": "Жетоны дружбы",
    "raid_tickets": "Билеты рейда", "campaign": "Кампания", "heroes": "Герои", "fortress": "Крепость", "summon": "Призыв",
    "modes": "Режимы", "chat": "Чат", "quests": "Задания", "mail": "Почта", "settings": "Настройки", "afk": "Дозор (AFK)",
    "events": "События / пропуск", "friends": "Друзья", "guild": "Гильдия", "shop": "Магазин", "arena": "Арена",
}
CHAT_UI = [
    ("panel.png", "Рамка окна чата", "1024×1536", "ornate rectangular window frame, thick gold border with Bashkir ornament, small turquoise diamonds in corners, crest at the top center, dark teal empty center, transparent background"),
    ("title_plaque.png", "Табличка заголовка", "880×200", "horizontal title plaque, dark teal glass center, gold ornamental frame with pointed diamond ends, transparent background"),
    ("tab.png", "Вкладка", "600×200", "game tab button, dark teal background, thin gold frame with angled corners, transparent background"),
    ("tab_active.png", "Активная вкладка", "600×200", "selected game tab button, warm golden glow, bright gold frame with angled corners, transparent background"),
    ("bubble.png", "Пузырь сообщения", "512×256", "chat speech bubble, dark translucent teal glass, thin turquoise and gold border, small tail top left, transparent background"),
    ("bubble_mine.png", "Ваше сообщение", "512×256", "chat speech bubble, dark amber glass, thin gold border, small tail top left, transparent background"),
    ("avatar_ring.png", "Кольцо аватара", "256×256", "circular avatar frame, gold ring with Bashkir ornament, turquoise gem at the bottom, empty transparent center"),
    ("background.png", "Фон ленты сообщений", "1024×1536", "night Ural mountains landscape, dark moody teal sky, misty valleys, very dark and low contrast"),
    ("event_raids.png", "Баннер события: рейд", "1024×256", "wide banner, giant stone golem with glowing turquoise runes on the right, dark teal background fading to the left"),
    ("event_tournaments.png", "Баннер события: турнир", "1024×256", "wide banner, crossed golden sabers and a trophy on the right, fading to the left"),
    ("event_events.png", "Баннер события мира", "1024×256", "wide banner, dark army under Toratau mountain in purple fog on the right, fading to the left"),
    ("event_guild.png", "Баннер события гильдии", "1024×256", "wide banner, golden guild banner with eagle emblem on the right, fading to the left"),
]
SCREENS = [
    ("boot_bg.png", "Фон стартового экрана", "1080×1920", "epic vertical key art, Ural mountains at dawn, Toratau shikhan, ancient fortress, heroic silhouettes, cinematic light"),
    ("logo.png", "Логотип «Уралия»", "1024×512", "game logo plate for the word URALIA, golden ornate frame with mountains, turquoise gems, empty space for the title, transparent background"),
]


def catalog() -> list[dict]:
    sections = [{"id": "heroes", "title": "Герои", "hint": "Портреты используются в чате, на карточках героев, в бою и в профиле. Квадрат, герой по пояс, лицо в центре.", "slots": []},
                {"id": "bosses", "title": "Враги и рейд-боссы", "hint": "Портреты врагов и боссов для карточек этапов и рейдов.", "slots": []},
                {"id": "icons", "title": "Иконки", "hint": "Иконки валют, разделов и кнопок. Квадрат 256×256, прозрачный фон, крупный читаемый силуэт.", "slots": []},
                {"id": "chat", "title": "Оформление чата", "hint": "Элементы экрана чата. Рамки и кнопки растягиваются (9-slice), поэтому края и углы должны быть цельными.", "slots": []},
                {"id": "screens", "title": "Экраны и фоны", "hint": "Стартовый экран и логотип.", "slots": []}]
    by = {s["id"]: s for s in sections}
    for h in D.HEROES:
        enemy = h.get("is_enemy")
        sec = by["bosses" if enemy else "heroes"]
        lore = (h.get("lore") or h.get("title") or "")[:160]
        prompt = (f"portrait of {h['name']} ({h.get('title') or ''}), fantasy {h.get('class_code', 'hero')}, "
                  f"faction {h.get('faction_code', '')}, bust shot, facing the viewer, dramatic rim light, "
                  f"dark teal background with gold particles, {STYLE}")
        sec["slots"].append({"path": f"heroes/{h['code']}.png", "title": h["name"], "size": "512×512",
                             "advice": f"Портрет «{h['name']}». {lore}".strip(), "prompt": prompt})
    for kind, name in ICON_KINDS.items():
        by["icons"]["slots"].append({"path": f"icons/{kind}.png", "title": name, "size": "256×256",
                                     "advice": f"Иконка «{name}». Должна читаться в размере 48 px.",
                                     "prompt": f"game icon for '{name}' ({kind.replace('_', ' ')}), single object, bold silhouette, gold and turquoise, soft glow, transparent background, {STYLE}"})
    for f, title, size, p in CHAT_UI:
        by["chat"]["slots"].append({"path": f"ui/chat/{f}", "title": title, "size": size, "advice": f"{title}, {size}.",
                                    "prompt": f"{p}, {STYLE}"})
    for f, title, size, p in SCREENS:
        by["screens"]["slots"].append({"path": f"ui/{f}", "title": title, "size": size, "advice": f"{title}, {size}.",
                                       "prompt": f"{p}, {STYLE}"})
    return sections


def slot_paths() -> set[str]:
    return {s["path"] for sec in catalog() for s in sec["slots"]}


# ------------------------------------------------------------------ staging
def staging() -> Path:
    p = get_settings().content_store_path / "art_staging"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _index_path() -> Path:
    return staging() / "index.json"


def index() -> dict:
    try:
        return json.loads(_index_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"files": {}, "published_version": 0, "published_at": None}


def _save_index(idx: dict) -> None:
    _index_path().write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")


def image_size(data: bytes) -> tuple[str, int, int] | None:
    """Detects PNG / JPEG / WEBP and returns (format, width, height) from the header (no imaging library)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 24:
        w, h = struct.unpack(">II", data[16:24])
        return "png", w, h
    if data[:3] == b"\xff\xd8\xff":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return "jpg", w, h
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg
        return "jpg", 0, 0
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        if data[12:16] == b"VP8X":
            w = 1 + int.from_bytes(data[24:27], "little")
            h = 1 + int.from_bytes(data[27:30], "little")
            return "webp", w, h
        return "webp", 0, 0
    return None


def stage(path: str, data: bytes) -> dict:
    if path not in slot_paths():
        raise ValueError("Неизвестный слот графики")
    if len(data) > MAX_BYTES:
        raise ValueError("Файл больше 8 МБ")
    info = image_size(data)
    if info is None:
        raise ValueError("Нужен PNG, JPG или WEBP")
    fmt, w, h = info
    if fmt != "png":
        raise ValueError("Загрузите PNG (для прозрачности и надёжной загрузки в игре)")
    dst = staging() / path
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    idx = index()
    idx["files"][path] = {"size": len(data), "width": w, "height": h, "uploaded_at": utcnow().isoformat(), "published": False}
    _save_index(idx)
    return idx["files"][path]


def unstage(path: str) -> None:
    idx = index()
    if path in idx["files"]:
        (staging() / path).unlink(missing_ok=True)
        del idx["files"][path]
        idx["dirty"] = True
        _save_index(idx)


def staged_file(path: str) -> Path | None:
    p = staging() / path
    return p if path in index()["files"] and p.is_file() else None


def publish(db: Session, admin: str) -> dict:
    """Builds the full ui.art package from every staged file and publishes it to the dev channel."""
    from ..content import pack, service
    idx = index()
    files = {}
    for path in sorted(idx["files"]):
        f = staging() / path
        if f.is_file():
            files[f"art/{path}"] = f.read_bytes()
    from sqlalchemy import func, select
    from ..models import ContentPackageVersion
    last = db.scalar(select(func.max(ContentPackageVersion.version)).where(ContentPackageVersion.package_id == PACKAGE_ID)) or 0
    version = max(int(idx.get("published_version", 0)), int(last)) + 1
    meta = {"package_id": PACKAGE_ID, "version": version, "kind": "ui", "title": "Графика из админ-панели",
            "min_client_version": "0.6.3", "dependencies": [], "required": False}
    if not files:
        files["art/README.txt"] = "Графика из админ-панели пока не загружена.".encode()
    data = pack.build(meta, files)
    pack.validate(data)
    m = service.publish(db, data, channel="dev", notes=f"art v{version}: {len(files)} файлов", admin=admin)
    idx["published_version"] = version
    idx["published_at"] = utcnow().isoformat()
    idx["dirty"] = False
    for v in idx["files"].values():
        v["published"] = True
    _save_index(idx)
    return {"version": version, "files": len(files), "manifest": m.version}
