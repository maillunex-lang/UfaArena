"""Game interface layout editor (admin «Редактор игры» → «Интерфейс»).

The client builds its main screens from a layout the server sends: the bottom navigation bar, the main screen (block
order, the two side columns of quick buttons, the big action buttons) and the «Ещё» screen (groups and tiles). The
admin can reorder buttons, move them between columns and groups, rename them, change icons, colours and sizes, hide
them, add buttons for other screens and add groups. Every save keeps the previous version (rollback) and is logged.

Safety: buttons only open existing screens (fixed registry below), «Главная» and «Ещё» can never be hidden from the bar
(so no one is locked out), unknown ids are rejected here and skipped by the client. Without a saved layout the client
shows exactly the built-in one (DEFAULT mirrors the client code)."""
from __future__ import annotations

import copy
import re
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.db import get_db, utcnow
from ..core.deps import player
from ..core.errors import GameError
from ..models import AdminAction, ServerSetting
from ..modules.admin import admin

KEY = "ui_layout"
HIST = "ui_layout_history"

# What a button can do: id -> (default label, default icon, kind). kind: screen | special | locked.
TARGETS: dict[str, tuple[str, str, str]] = {
    "home": ("Главная", "home", "screen"), "heroes": ("Герои", "heroes", "screen"), "campaign": ("Поход", "campaign", "screen"),
    "guild": ("Гильдия", "guild", "screen"), "world": ("Мир", "world", "screen"), "more": ("Ещё", "more", "screen"),
    "quests": ("Задания", "quests", "screen"), "achievements": ("Достижения", "ranks", "screen"),
    "mail": ("Почта", "mail", "screen"), "friends": ("Друзья", "friends", "screen"), "chat": ("Чат", "chat", "special"),
    "caravan": ("Караван", "caravan", "screen"), "events": ("События", "events", "screen"), "afk": ("Дозор", "afk", "special"),
    "raids": ("Рейды", "shulgan", "screen"), "arena": ("Арена", "arena", "screen"), "tournaments": ("Турниры", "crown", "screen"),
    "shop": ("Магазин", "shop", "screen"), "summon": ("Призыв", "summon", "screen"), "battle": ("В бой", "arena", "special"),
    "rankings": ("Рейтинг", "ranks", "screen"), "inventory": ("Инвентарь", "quests", "screen"),
    "formation": ("Отряд", "heroes", "screen"), "profile": ("Профиль", "profile", "screen"),
    "settings": ("Настройки", "settings", "screen"), "search": ("Поиск", "search", "special"),
    "equipment": ("Экипировка", "lock", "locked"), "artifacts": ("Артефакты", "lock", "locked"),
}
# built-in vector icons of the client (GameIcon.kind); each can also be replaced by a PNG in «Графика» → icons/<kind>.png
ICONS = ["gold", "crystals", "summon_essence", "ancient_seals", "guild_marks", "nature_essence", "campaign", "heroes",
         "fortress", "summon", "modes", "quests", "mail", "settings", "afk", "events", "friends", "chat", "crown", "home",
         "world", "more", "bell", "ranks", "guild", "shop", "arena", "profile", "lock", "search", "caravan", "stone_sky",
         "living_kurai", "ashen_reach", "shulgan"]
BLOCKS = {"campaign": "Полоса похода (прогресс кампании)", "middle": "Боковые кнопки и отряд",
          "daily": "Ежедневные задания", "actions": "Большие кнопки"}
NAV_REQUIRED = ("home", "more")
# every screen of the client (Main.SCREENS) + «main» — the shell around them (top bar); rules for any button / text there
SCREEN_IDS = {"main": "Верхняя панель (поверх всех экранов)", "home": "Главная", "heroes": "Герои", "formation": "Отряд",
              "summon": "Призыв", "campaign": "Поход", "caravan": "Караван", "quests": "Задания", "mail": "Почта",
              "shop": "Магазин", "chat": "Чат", "friends": "Друзья", "guild": "Гильдия", "raids": "Рейды",
              "arena": "Арена", "tournaments": "Турниры", "events": "События", "rankings": "Рейтинг", "world": "Мир",
              "more": "Ещё", "profile": "Профиль", "inventory": "Инвентарь", "settings": "Настройки"}
RULE_KINDS = ("button", "label")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _it(i: str, **kw) -> dict:
    lbl, ic, _ = TARGETS[i]
    return {"id": i, "label": lbl, "icon": ic, "hidden": False, **kw}


DEFAULT: dict = {
    "nav": [_it(i) for i in ("home", "heroes", "campaign", "guild", "world", "more")],
    "home": {
        "blocks": [{"id": b, "hidden": False} for b in BLOCKS],
        "left": [_it(i) for i in ("quests", "mail", "friends", "chat", "caravan")],
        "right": [_it(i) for i in ("events", "afk", "raids", "arena", "tournaments")],
        "actions": [_it("shop", color="#1d4f8a", ratio=1.0), _it("summon", color="#4b2a7a", ratio=1.0),
                    _it("battle", color="#8e1b1b", ratio=1.5)],
    },
    "more": {"columns": 3, "groups": [
        {"title": "Предметы", "items": [_it("inventory"), _it("equipment"), _it("artifacts")]},
        {"title": "Прогресс", "items": [_it("summon"), _it("quests"), _it("achievements")]},
        {"title": "Социальное и сервисы", "items": [_it(i) for i in ("mail", "shop", "rankings", "friends", "chat", "caravan")]},
        {"title": "Управление", "items": [_it("profile"), _it("settings")]},
    ]},
}


def _bad(msg: str):
    raise GameError("bad_layout", msg, 400)


def _item(x, where: str, extra: tuple = ()) -> dict:
    if not isinstance(x, dict) or x.get("id") not in TARGETS:
        _bad(f"{where}: неизвестная кнопка {x.get('id') if isinstance(x, dict) else x!r}")
    lbl = str(x.get("label") or TARGETS[x["id"]][0]).strip()
    if not 1 <= len(lbl) <= 20:
        _bad(f"{where}: подпись «{lbl}» — от 1 до 20 символов")
    icon = x.get("icon") or TARGETS[x["id"]][1]
    if icon not in ICONS:
        _bad(f"{where}: неизвестная иконка {icon}")
    out = {"id": x["id"], "label": lbl, "icon": icon, "hidden": bool(x.get("hidden", False))}
    if "color" in extra:
        c = x.get("color") or "#1d4f8a"
        if not HEX.match(c):
            _bad(f"{where}: цвет в формате #RRGGBB")
        out["color"] = c
    if "ratio" in extra:
        try:
            r = round(float(x.get("ratio", 1.0)), 2)
        except (TypeError, ValueError):
            r = -1
        if not 0.5 <= r <= 3.0:
            _bad(f"{where}: ширина от 0.5 до 3")
        out["ratio"] = r
    return out


def _list(xs, where: str, lo: int, hi: int, extra: tuple = (), unique: bool = True) -> list[dict]:
    if not isinstance(xs, list) or not lo <= len(xs) <= hi:
        _bad(f"{where}: от {lo} до {hi} кнопок")
    out = [_item(x, where, extra) for x in xs]
    ids = [o["id"] for o in out]
    if unique and len(set(ids)) != len(ids):
        _bad(f"{where}: одна кнопка указана дважды")
    return out


def validate(v: dict) -> dict:
    if not isinstance(v, dict):
        _bad("Ожидается объект раскладки")
    nav = _list(v.get("nav"), "Нижняя панель", 2, 7)
    for req in NAV_REQUIRED:
        if not any(n["id"] == req and not n["hidden"] for n in nav):
            _bad(f"Нижняя панель: кнопку «{TARGETS[req][0]}» нельзя убрать — иначе игрок не сможет вернуться")
    for n in nav:
        if TARGETS[n["id"]][2] != "screen":
            _bad(f"Нижняя панель: «{n['label']}» — только кнопки разделов")
    h = v.get("home") or {}
    blocks = h.get("blocks")
    if not isinstance(blocks, list) or sorted(b.get("id") for b in blocks if isinstance(b, dict)) != sorted(BLOCKS):
        _bad("Главный экран: нужен каждый блок ровно один раз")
    home = {"blocks": [{"id": b["id"], "hidden": bool(b.get("hidden", False))} for b in blocks],
            "left": _list(h.get("left"), "Левая колонка", 0, 7), "right": _list(h.get("right"), "Правая колонка", 0, 7),
            "actions": _list(h.get("actions"), "Большие кнопки", 1, 4, ("color", "ratio"))}
    side = [i["id"] for i in home["left"] + home["right"]]
    if len(set(side)) != len(side):
        _bad("Главный экран: кнопка стоит в обеих колонках")
    for i in home["left"] + home["right"] + home["actions"]:
        if TARGETS[i["id"]][2] == "locked":
            _bad(f"Главный экран: «{i['label']}» ещё не работает в игре")
    m = v.get("more") or {}
    cols = m.get("columns", 3)
    if cols not in (2, 3, 4):
        _bad("«Ещё»: колонок 2, 3 или 4")
    groups = m.get("groups")
    if not isinstance(groups, list) or not 1 <= len(groups) <= 10:
        _bad("«Ещё»: от 1 до 10 групп")
    gout = []
    for g in groups:
        t = str((g or {}).get("title", "")).strip()
        if not 1 <= len(t) <= 32:
            _bad("«Ещё»: название группы от 1 до 32 символов")
        gout.append({"title": t, "items": _list(g.get("items"), f"«Ещё» → {t}", 0, 12)})
    allm = [i["id"] for g in gout for i in g["items"]]
    if len(set(allm)) != len(allm):
        _bad("«Ещё»: кнопка стоит в двух группах")
    out = {"nav": nav, "home": home, "more": {"columns": cols, "groups": gout}}
    if v.get("screens"):
        out["screens"] = _screens(v["screens"])
    return out


def _screens(sc) -> dict:
    """Rules over the real interface of any screen: a button or text is found by its caption (digits ignored) and can
    be hidden, renamed, recoloured, moved among its neighbours, or sent to another screen («куда ведёт»)."""
    if not isinstance(sc, dict):
        _bad("screens: ожидается объект {экран: {rules: [...]}}")
    out = {}
    for sid, body in sc.items():
        if sid not in SCREEN_IDS:
            _bad(f"Неизвестный экран «{sid}» (есть: {', '.join(SCREEN_IDS)})")
        rules = (body or {}).get("rules", [])
        if not isinstance(rules, list) or len(rules) > 200:
            _bad(f"{SCREEN_IDS[sid]}: до 200 правил")
        seen, clean = set(), []
        for r in rules:
            if not isinstance(r, dict):
                _bad(f"{SCREEN_IDS[sid]}: правило — объект")
            key = str(r.get("key", "")).strip()
            kind = r.get("kind", "button")
            if not 1 <= len(key) <= 80 or kind not in RULE_KINDS:
                _bad(f"{SCREEN_IDS[sid]}: у правила нужен key (текст элемента, до 80) и kind button|label")
            if (kind, key) in seen:
                _bad(f"{SCREEN_IDS[sid]}: правило для «{key}» указано дважды")
            seen.add((kind, key))
            lbl = str(r.get("label") or "").strip()
            if len(lbl) > 40:
                _bad(f"{SCREEN_IDS[sid]} «{key}»: новая подпись до 40 символов")
            color = r.get("color") or ""
            if color and not HEX.match(color):
                _bad(f"{SCREEN_IDS[sid]} «{key}»: цвет #RRGGBB")
            action = r.get("action") or ""
            if action and kind != "button":
                _bad(f"{SCREEN_IDS[sid]} «{key}»: «куда ведёт» — только у кнопок")
            if action and action != "none" and (action not in TARGETS or TARGETS[action][2] == "locked"):
                _bad(f"{SCREEN_IDS[sid]} «{key}»: неизвестное действие «{action}»")
            try:
                move = int(r.get("move") or 0)
            except (TypeError, ValueError):
                move = 99
            if not -20 <= move <= 20:
                _bad(f"{SCREEN_IDS[sid]} «{key}»: сдвиг -20…20")
            rule = {"key": key, "kind": kind, "hidden": bool(r.get("hidden", False)), "label": lbl, "color": color,
                    "action": action, "move": move}
            if any(rule[k] for k in ("hidden", "label", "color", "action", "move")):
                clean.append(rule)
        if clean:
            out[sid] = {"rules": clean}
    return out


def get(db: Session) -> dict:
    """The live layout (the built-in one when nothing was saved) with its version (0 = built-in)."""
    row = db.get(ServerSetting, KEY)
    if row and row.value and row.value.get("layout"):
        return {"version": int(row.value.get("version", 1)), "layout": copy.deepcopy(row.value["layout"])}
    return {"version": 0, "layout": copy.deepcopy(DEFAULT)}


def save(db: Session, layout: dict | None, who: str, action: str = "ui_layout_save") -> dict:
    cur = get(db)
    hist = db.get(ServerSetting, HIST)
    if hist is None:
        hist = ServerSetting(key=HIST, value={"items": []})
        db.add(hist)
    hist.value = {"items": (list((hist.value or {}).get("items", [])) + [
        {"at": utcnow().isoformat(), "by": who, "action": action, "data": cur}])[-30:]}
    row = db.get(ServerSetting, KEY)
    if row is None:
        row = ServerSetting(key=KEY, value={})
        db.add(row)
    ver = max(cur["version"], max((int(h["data"].get("version", 0)) for h in hist.value["items"]), default=0)) + 1
    row.value = {"version": ver, "layout": layout} if layout is not None else {"version": ver, "layout": copy.deepcopy(DEFAULT)}
    db.add(AdminAction(admin=who, action=action, details={"version": ver}))
    db.flush()
    return get(db)


def history(db: Session) -> list[dict]:
    hist = db.get(ServerSetting, HIST)
    return [{"at": h["at"], "by": h["by"], "action": h["action"], "version": h["data"].get("version", 0)}
            for h in (hist.value or {}).get("items", [])] if hist else []


def rollback(db: Session, who: str) -> dict:
    hist = db.get(ServerSetting, HIST)
    items = list((hist.value or {}).get("items", [])) if hist else []
    if not items:
        raise GameError("no_history", "Нет предыдущей версии", 400)
    prev = items.pop()
    hist.value = {"items": items}
    row = db.get(ServerSetting, KEY)
    newver = int((row.value or {}).get("version", 0)) + 1  # clients compare versions: always move forward
    row.value = {"version": newver, "layout": prev["data"]["layout"]}
    db.add(AdminAction(admin=who, action="ui_layout_rollback", details={"to": prev["at"], "version": newver}))
    db.flush()
    return get(db)


# ------------------------------------------------------------------ interface map (screenshots + elements)
MAP_DEFAULT = Path(__file__).resolve().parents[1] / "game" / "content" / "ui_map"
MAPPERS = "ui_mappers"


def _map_dir():
    from ..core.config import get_settings
    p = get_settings().content_store_path / "ui_map"
    p.mkdir(parents=True, exist_ok=True)
    return p


def map_file(screen: str, ext: str):
    """The latest map uploaded by a mapper; the one shipped with the code otherwise."""
    for d in (_map_dir(), MAP_DEFAULT):
        f = d / f"{screen}.{ext}"
        if f.is_file():
            return f
    return None


def map_index() -> dict:
    import json as _json
    out = {}
    for sid, title in SCREEN_IDS.items():
        f = map_file(sid, "json")
        if f is None:
            out[sid] = {"title": title, "elements": [], "image": False}
            continue
        d = _json.loads(f.read_text(encoding="utf-8"))
        out[sid] = {"title": title, "elements": d.get("elements", [])[:400], "image": map_file(sid, "jpg") is not None,
                    "at": d.get("at"), "by": d.get("by"), "client": d.get("client"),
                    "source": "uploaded" if f.parent == _map_dir() else "bundled"}
    return out


def mappers(db: Session) -> list[str]:
    row = db.get(ServerSetting, MAPPERS)
    return list((row.value or {}).get("users", [])) if row else []


def is_mapper(db: Session, user_id: str) -> bool:
    return user_id in mappers(db)


# ------------------------------------------------------------------ API
router = APIRouter(prefix="/admin/api/game/layout", tags=["game-editor"])
public = APIRouter(tags=["release"])


@public.get("/client/layout")
def client_layout(db: Session = Depends(get_db)):
    """The interface layout for the game client (no login needed: it is not secret, the menu is the same for all)."""
    return get(db)


@router.get("")
def admin_layout(_: str = Depends(admin), db: Session = Depends(get_db)):
    targets = [{"id": k, "label": v[0], "icon": v[1], "kind": v[2]} for k, v in TARGETS.items()]
    return {**get(db), "default": DEFAULT, "targets": targets, "icons": ICONS, "screens": SCREEN_IDS,
            "blocks": [{"id": k, "title": v} for k, v in BLOCKS.items()], "history": history(db)}


class LayoutIn(BaseModel):
    layout: dict


@router.post("")
def admin_save(body: LayoutIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    out = save(db, validate(body.layout), who)
    db.commit()
    return out


@router.post("/reset")
def admin_reset(who: str = Depends(admin), db: Session = Depends(get_db)):
    out = save(db, None, who, "ui_layout_reset")
    db.commit()
    return out


@router.get("/map")
def admin_map(_: str = Depends(admin), db: Session = Depends(get_db)):
    from ..models import PlayerProfile
    names = []
    for uid in mappers(db):
        p = db.get(PlayerProfile, uid)
        if p:
            names.append({"uralia_id": p.uralia_id, "nickname": p.nickname})
    return {"screens": map_index(), "mappers": names}


@router.get("/map/{screen}.jpg")
def admin_map_image(screen: str, _: str = Depends(admin)):
    from fastapi.responses import FileResponse
    if screen not in SCREEN_IDS or (f := map_file(screen, "jpg")) is None:
        raise GameError("not_found", "Нет снимка экрана", 404)
    return FileResponse(f, media_type="image/jpeg")


class MapperIn(BaseModel):
    uralia_id: str
    on: bool


@router.post("/mappers")
def admin_mappers(body: MapperIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    """A trusted player (usually the owner's own account) who may upload the interface map from the game."""
    from sqlalchemy import select as _select
    from ..models import PlayerProfile
    p = db.scalar(_select(PlayerProfile).where(PlayerProfile.uralia_id == body.uralia_id.strip()))
    if p is None or p.is_ai:
        raise GameError("not_found", "Игрок не найден (нужен Uralia ID реального игрока)", 404)
    users = [u for u in mappers(db) if u != p.user_id] + ([p.user_id] if body.on else [])
    row = db.get(ServerSetting, MAPPERS)
    if row is None:
        row = ServerSetting(key=MAPPERS, value={})
        db.add(row)
    row.value = {"users": users[-10:]}
    db.add(AdminAction(admin=who, action="ui_mapper", details={"uralia_id": p.uralia_id, "on": body.on}))
    db.commit()
    return {"ok": True}


class MapIn(BaseModel):
    screen: str
    elements: list[dict]
    image_b64: str = ""
    client: str = ""


@public.post("/client/ui-map")
def client_ui_map(body: MapIn, user=Depends(player),
                  db: Session = Depends(get_db)):
    """Upload of one screen of the interface map (screenshot + elements) by a player marked as a mapper."""
    import base64
    import json as _json
    if not is_mapper(db, user.id):
        raise GameError("forbidden", "Снимать карту интерфейса может только отмеченный в админке игрок", 403)
    if body.screen not in SCREEN_IDS or len(body.elements) > 600:
        raise GameError("bad_map", "Неизвестный экран или слишком много элементов", 400)
    els = []
    for e in body.elements:
        key = str(e.get("key", ""))[:80]
        r = e.get("rect") or []
        if not key or e.get("kind") not in RULE_KINDS or len(r) != 4:
            continue
        els.append({"key": key, "kind": e["kind"], "text": str(e.get("text", ""))[:120],
                    "rect": [round(min(1.0, max(0.0, float(x))), 4) for x in r], "count": int(e.get("count", 1))})
    d = _map_dir()
    if body.image_b64:
        img = base64.b64decode(body.image_b64[: 3_000_000])
        if img[:3] != b"\xff\xd8\xff":
            raise GameError("bad_map", "Снимок должен быть JPEG", 400)
        (d / f"{body.screen}.jpg").write_bytes(img)
    from ..models import PlayerProfile
    p = db.get(PlayerProfile, user.id)
    (d / f"{body.screen}.json").write_text(_json.dumps({"screen": body.screen, "elements": els, "at": utcnow().isoformat(),
                                                        "by": p.nickname if p else "", "client": body.client[:16]},
                                                       ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "elements": len(els)}


@router.post("/rollback")
def admin_rollback(who: str = Depends(admin), db: Session = Depends(get_db)):
    out = rollback(db, who)
    db.commit()
    return out
