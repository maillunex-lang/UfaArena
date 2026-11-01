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

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.db import get_db, utcnow
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
    return {"nav": nav, "home": home, "more": {"columns": cols, "groups": gout}}


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
    return {**get(db), "default": DEFAULT, "targets": targets, "icons": ICONS,
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


@router.post("/rollback")
def admin_rollback(who: str = Depends(admin), db: Session = Depends(get_db)):
    out = rollback(db, who)
    db.commit()
    return out
