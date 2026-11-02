"""ZIP patches for every admin setting (format «uralia-patch/1»).

Each setting in the admin panel (heroes, chapters and stages, maps, interface menu, AI settings, AI switches, shop
products, graphics slots) can be changed by hand or with a patch: a ZIP with `patch.json` (+ files for graphics) or the
bare JSON pasted in the panel. A patch is made by the owner or by an outside AI (Gemini, Claude, ChatGPT, Grok) from
the task template the panel generates for that setting (current values + field rules + the owner's wish).

Safety:
- every change goes through the SAME validation as the manual editors (the editor functions are reused);
- «Проверить» runs the whole patch in a transaction and rolls it back: the owner sees what would change, nothing is
  written; «Применить» applies all changes or none (one transaction; graphics files are written only after the
  database part succeeded);
- data only: no code, scripts or SQL are ever executed; ZIP limits (size, number of files, allowed extensions, paths);
- every applied patch is kept with a snapshot of what it touched, the last one can be rolled back; logged."""
from __future__ import annotations

import copy
import io
import json
import re
import secrets
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import get_db, utcnow
from ..core.errors import GameError
from ..models import (AdminAction, CampaignNode, CampaignRegion, Faction, Hero, HeroClass, PlayerCampaignProgress,
                      PlayerHero, ServerSetting, ShopProduct)
from ..modules.admin import admin
from . import campaign as CAMP
from . import layout as LAYOUT
from . import overrides as OV
from . import router as HER

FORMAT = "uralia-patch/1"
MAX_ZIP = 60 * 1024 * 1024
MAX_UNPACKED = 200 * 1024 * 1024
MAX_FILES = 200
MAX_CHANGES = 500
ALLOWED_EXT = {"json", "png", "jpg", "jpeg", "glb", "txt", "md"}
HIST = "patch_history"


class PatchError(ValueError):
    pass


class _Tx:
    """The editor functions commit; inside a patch a commit is only a flush, so the whole patch stays one transaction."""

    def __init__(self, db: Session):
        self._db = db

    def commit(self):
        self._db.flush()

    def __getattr__(self, name):
        return getattr(self._db, name)


# ------------------------------------------------------------------ reading
def read(data: bytes) -> tuple[dict, dict[str, bytes]]:
    """A ZIP with patch.json (+ files/…) or the bare JSON text. Returns (patch, files)."""
    files: dict[str, bytes] = {}
    if data[:2] == b"PK":
        if len(data) > MAX_ZIP:
            raise PatchError("Архив больше 60 МБ")
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise PatchError("Файл не похож на ZIP-архив")
        infos = [i for i in z.infolist() if not i.is_dir()]
        if len(infos) > MAX_FILES:
            raise PatchError(f"В архиве больше {MAX_FILES} файлов")
        if sum(i.file_size for i in infos) > MAX_UNPACKED:
            raise PatchError("Распакованный архив больше 200 МБ")
        names = [i.filename for i in infos]
        root = ""  # tolerate one wrapping folder (AI often zips «uralia_patch/patch.json»)
        if "patch.json" not in names:
            cands = [n for n in names if n.endswith("/patch.json") and n.count("/") == 1 and not n.startswith("__MACOSX")]
            if not cands:
                raise PatchError("В архиве нет patch.json")
            root = cands[0][: -len("patch.json")]
        for i in infos:
            n = i.filename
            if n.startswith("__MACOSX/") or n.endswith(".DS_Store"):
                continue
            if root and not n.startswith(root):
                continue
            rel = n[len(root):]
            if rel.startswith("/") or ".." in rel.split("/") or "\\" in rel:
                raise PatchError(f"Недопустимый путь в архиве: {n}")
            ext = rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
            if ext not in ALLOWED_EXT:
                raise PatchError(f"Недопустимый тип файла в архиве: {rel} (разрешены: {', '.join(sorted(ALLOWED_EXT))})")
            files[rel] = z.read(i)
        raw = files.pop("patch.json")
    else:
        raw = data
    try:
        text = raw.decode("utf-8-sig").strip()
        if text.startswith("```"):  # pasted straight from an AI chat
            text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text)
        doc = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise PatchError(f"patch.json: не удалось прочитать JSON ({e})")
    if isinstance(doc, list):  # a bare list of changes
        doc = {"format": FORMAT, "changes": doc}
    if not isinstance(doc, dict) or doc.get("format", FORMAT) != FORMAT:
        raise PatchError(f"Неизвестный формат патча (нужен «{FORMAT}»)")
    ch = doc.get("changes")
    if not isinstance(ch, list) or not ch:
        raise PatchError("В патче нет изменений (changes)")
    if len(ch) > MAX_CHANGES:
        raise PatchError(f"Больше {MAX_CHANGES} изменений в одном патче")
    for i, c in enumerate(ch, 1):
        if not isinstance(c, dict) or c.get("type") not in TYPES:
            raise PatchError(f"Изменение №{i}: неизвестный type «{c.get('type') if isinstance(c, dict) else c}». "
                             f"Допустимо: {', '.join(TYPES)}")
    return doc, files


# ------------------------------------------------------------------ helpers
def _flat(v, prefix="") -> dict:
    out = {}
    if isinstance(v, dict):
        for k, x in v.items():
            out.update(_flat(x, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
        for i, x in enumerate(v):
            key = x.get("id") or x.get("hero_code") or x.get("title") or i
            out.update(_flat(x, f"{prefix}[{key}]"))
    else:
        out[prefix] = v
    return out


def diff(before, after, limit: int = 60) -> list[dict]:
    a, b = _flat(before or {}), _flat(after or {})
    out = []
    for k in list(dict.fromkeys([*a, *b])):
        if a.get(k) != b.get(k):
            out.append({"field": k, "before": a.get(k), "after": b.get(k)})
            if len(out) >= limit:
                break
    return out


def _gerr(e: Exception) -> str:
    if isinstance(e, GameError):
        return str((e.detail or {}).get("message") if isinstance(e.detail, dict) else e.detail)
    return str(e)


def _need(c: dict, key: str, kind=str):
    v = c.get(key)
    if not isinstance(v, kind) or (kind is str and not v.strip()):
        raise PatchError(f"нужно поле «{key}»")
    return v


# ------------------------------------------------------------------ types
class T:
    """A patchable setting. state(db, c) -> dict for the before/after view; apply(db, c, who, ctx) changes it;
    keys(c) -> server_settings keys it touches (snapshot for rollback); export(db, id) -> current state as changes;
    ids(db) -> [(id, title)]; doc(db) -> field rules (Russian) for the AI task."""
    title = ""
    obj = ""

    def label(self, c: dict) -> str:
        return str(c.get(self.obj, "")) if self.obj else ""

    def keys(self, c: dict) -> list[str]:
        return []


def _hero_fields(h: Hero) -> dict:
    out = {k: copy.deepcopy(getattr(h, k)) for k in HER.HERO_FIELDS}
    if isinstance(out.get("extra"), dict):
        out["extra"].pop("disabled", None)  # service flag of the override layer, shown as the top-level «disabled»
    return out


class HeroT(T):
    title, obj = "Герой / враг", "code"

    def state(self, db, c):
        h = db.get(Hero, c.get("code", ""))
        if h is None:
            return None
        return {**_hero_fields(h), "disabled": bool((OV.get(db)["heroes"].get(h.code) or {}).get("disabled"))}

    def keys(self, c):
        return [OV.KEY]

    def apply(self, db, c, who, ctx):
        code = _need(c, "code")
        f = c.get("fields") or {}
        if not isinstance(f, dict):
            raise PatchError("fields должно быть объектом")
        if db.get(Hero, code) is None:
            HER.create_hero(HER.HeroIn(code=code, fields=f), who, db)
            ctx["created"].setdefault("heroes", []).append(code)
        elif f:
            HER.edit_hero(code, HER.HeroIn(code=code, fields=f), who, db)
        if "disabled" in c:
            HER.disable_hero(code, HER.DisableIn(disabled=bool(c["disabled"])), who, db)

    def ids(self, db):
        return [(h.code, f"{h.name}{' (враг)' if h.is_enemy else ''}") for h in db.scalars(select(Hero).order_by(Hero.is_enemy, Hero.name))]

    def export(self, db, id_):
        q = select(Hero).order_by(Hero.is_enemy, Hero.name) if id_ in ("*", "") else select(Hero).where(Hero.code == id_)
        dis = OV.get(db)["heroes"]
        return [{"type": "hero", "code": h.code, "fields": _hero_fields(h), "disabled": bool((dis.get(h.code) or {}).get("disabled"))}
                for h in db.scalars(q)]

    def doc(self, db):
        fac = ", ".join(f"{f.code} ({f.name})" for f in db.scalars(select(Faction)))
        cls = ", ".join(f"{c.code} ({c.name})" for c in db.scalars(select(HeroClass)))
        lim = "; ".join(f"{k}: {lo}…{hi}" for k, (lo, hi) in HER.LIMITS.items())
        kinds = ", ".join(f"{k} ({v})" for k, v in HER.SKILL_KINDS.items())
        return f"""Изменение `{{"type": "hero", "code": "<код>", "fields": {{…}}, "disabled": false}}`.
- `code` — код героя (латиница в нижнем регистре, цифры, «_», 3–41 символ). Существующий код — правка; новый код —
  создание героя (тогда обязательны: name, faction_code, class_code, rarity, base_hp, base_atk, base_def, base_spd).
- В `fields` можно указать только изменяемые поля — остальные останутся как есть.
- Поля: name (до 64), title (до 128), faction_code, class_code, rarity, base_hp, base_atk, base_def, base_spd,
  skill {{kind, name, power, desc…}}, model, lore (до 4000), is_enemy, summonable, role, kit (набор умений v3), extra
  (crit, crit_dmg, growth, range, role_name…).
- Диапазоны: {lim}.
- Фракции: {fac}.
- Классы: {cls}.
- Вид умения skill.kind: {kinds} (или "kit" для героев с набором умений).
- 3D-модель model: {", ".join(HER.RIGS)}.
- `disabled: true` — убрать героя из призыва и каталога (у игроков, которые его получили, он остаётся). Удалять героев
  патчем нельзя."""


class RegionT(T):
    title, obj = "Глава кампании", "code"

    def state(self, db, c):
        r = db.get(CampaignRegion, c.get("code", ""))
        return CAMP._region_view(db, r, OV.get(db)["regions"]) if r else None

    def keys(self, c):
        return [OV.KEY]

    def apply(self, db, c, who, ctx):
        code = _need(c, "code")
        f = c.get("fields") or {}
        if db.get(CampaignRegion, code) is None:
            CAMP.create_region(CAMP.ItemIn(code=code, fields=f), who, db)
            ctx["created"].setdefault("regions", []).append(code)
        elif f:
            CAMP.edit_region(code, CAMP.ItemIn(code=code, fields=f), who, db)
        if "hidden" in c:
            CAMP.hide_region(code, CAMP.HideIn(hidden=bool(c["hidden"])), who, db)

    def ids(self, db):
        return [(r.code, f"{r.order}. {r.name}") for r in db.scalars(select(CampaignRegion).order_by(CampaignRegion.order))]

    def export(self, db, id_):
        q = select(CampaignRegion).order_by(CampaignRegion.order)
        if id_ not in ("*", ""):
            q = q.where(CampaignRegion.code == id_)
        ov = OV.get(db)["regions"]
        return [{"type": "region", "code": r.code, "fields": {"name": r.name, "order": r.order, "real_place": r.real_place,
                 "description": r.description}, "hidden": bool((ov.get(r.code) or {}).get("hidden"))} for r in db.scalars(q)]

    def doc(self, db):
        return """Изменение `{"type": "region", "code": "<код главы>", "fields": {…}, "hidden": false}`.
- Новый код (латиница/цифры/«_», 3–32) — новая глава (обязательно name и order).
- Поля: name (до 128), order (1…1000), real_place (до 255 — реальное место Южного Урала), description (до 4000).
- `hidden: true` — скрыть главу (прогресс игроков сохраняется). Удалять главы нельзя."""


class NodeT(T):
    title, obj = "Этап кампании", "code"
    FIELDS = ("name", "region_code", "order", "territory", "real_place", "is_boss", "rewards", "first_clear_rewards",
              "map_pos", "enemies", "story")

    def state(self, db, c):
        n = db.get(CampaignNode, c.get("code", ""))
        if n is None:
            return None
        v = CAMP._node_view(db, n, OV.get(db)["nodes"])
        v.pop("players_cleared", None)
        return v

    def keys(self, c):
        return [OV.KEY]

    def apply(self, db, c, who, ctx):
        code = _need(c, "code")
        f = c.get("fields") or {}
        if db.get(CampaignNode, code) is None:
            CAMP.create_node(CAMP.ItemIn(code=code, fields=f), who, db)
            ctx["created"].setdefault("nodes", []).append(code)
        elif f:
            CAMP.edit_node(code, CAMP.ItemIn(code=code, fields=f), who, db)
        if "hidden" in c:
            CAMP.hide_node(code, CAMP.HideIn(hidden=bool(c["hidden"])), who, db)

    def ids(self, db):
        return [(n.code, f"{n.region_code} · {n.order}. {n.name}") for n in
                db.scalars(select(CampaignNode).order_by(CampaignNode.region_code, CampaignNode.order))]

    def export(self, db, id_):
        q = select(CampaignNode).order_by(CampaignNode.region_code, CampaignNode.order)
        if id_.startswith("region:"):
            q = q.where(CampaignNode.region_code == id_[7:])
        elif id_ not in ("*", ""):
            q = q.where(CampaignNode.code == id_)
        ov = OV.get(db)["nodes"]
        return [{"type": "node", "code": n.code, "fields": {k: getattr(n, k) for k in self.FIELDS},
                 "hidden": bool((ov.get(n.code) or {}).get("hidden"))} for n in db.scalars(q)]

    def doc(self, db):
        enemies = ", ".join(h.code for h in db.scalars(select(Hero).where(Hero.is_enemy.is_(True)).order_by(Hero.code)))
        return f"""Изменение `{{"type": "node", "code": "<код этапа>", "fields": {{…}}, "hidden": false}}`.
- Новый код — новый этап (обязательно name, region_code, enemies).
- Поля: name (до 128), region_code (код главы), order (1…1000), territory ({", ".join(CAMP.TERRITORIES)}),
  real_place (до 255), is_boss (true/false), rewards и first_clear_rewards — {{валюта: количество}}, валюты:
  {", ".join(CAMP.CURRENCIES)} (целые 0…1 000 000), map_pos [x, y] (-100…100, клетки карты главы),
  enemies — 1…5 врагов [{{"hero_code": "…", "level": 1…200, "slot": 0…4}}] (слоты без повторов, 0–1 — передний ряд),
  story — до 30 реплик [{{"speaker": "…", "text": "до 600 символов"}}], говорящие: {", ".join(CAMP.SPEAKERS)}.
- Коды врагов: {enemies}. Можно ставить и героев-союзников (любой код героя).
- `hidden: true` — скрыть этап (пройденный этап остаётся пройденным). Удалять этапы нельзя."""


class NodeOrderT(T):
    title, obj = "Порядок этапов главы", "region_code"

    def state(self, db, c):
        rc = c.get("region_code", "")
        return {"codes": [n.code for n in db.scalars(select(CampaignNode).where(CampaignNode.region_code == rc).order_by(CampaignNode.order))]}

    def keys(self, c):
        return [OV.KEY]

    def apply(self, db, c, who, ctx):
        CAMP.reorder(CAMP.ReorderIn(region_code=_need(c, "region_code"), codes=_need(c, "codes", list)), who, db)

    def ids(self, db):
        return RegionT().ids(db)

    def export(self, db, id_):
        regs = [r.code for r in db.scalars(select(CampaignRegion).order_by(CampaignRegion.order))] if id_ in ("*", "") else [id_]
        return [{"type": "node_order", "region_code": r, **self.state(db, {"region_code": r})} for r in regs]

    def doc(self, db):
        return """Изменение `{"type": "node_order", "region_code": "<глава>", "codes": ["этап1", "этап2", …]}` — новый
порядок прохождения этапов главы (все коды из этой главы)."""


class MapT(T):
    title, obj = "Карты (точки этапов и глав)", ""

    def state(self, db, c):
        o = OV.get(db)
        return {"nodes": {n.code: n.map_pos for n in db.scalars(select(CampaignNode))},
                "world": {**OV.WORLD_DEFAULT, **(o.get("world_map") or {})}}

    def keys(self, c):
        return [OV.KEY]

    def apply(self, db, c, who, ctx):
        if c.get("nodes"):
            CAMP.save_node_positions(CAMP.NodePositionsIn(positions=c["nodes"]), who, db)
        if c.get("world"):
            CAMP.save_world_positions(CAMP.WorldPositionsIn(positions=c["world"]), who, db)
        if not c.get("nodes") and not c.get("world"):
            raise PatchError("нужно nodes и/или world")

    def ids(self, db):
        return [("*", "Все карты")]

    def export(self, db, id_):
        return [{"type": "map", **self.state(db, {})}]

    def doc(self, db):
        return """Изменение `{"type": "map", "nodes": {"<этап>": [x, y]}, "world": {"<глава>": [x, y]}}`.
- nodes — точки этапов на карте главы: целые клетки -60…60.
- world — положение глав на карте мира: доли 0…1 (0,0 — левый верхний угол; север сверху).
- Можно указать только то, что меняется."""


class LayoutT(T):
    title, obj = "Интерфейс: кнопки и экраны", ""

    def state(self, db, c):
        return LAYOUT.get(db)["layout"]

    def keys(self, c):
        return [LAYOUT.KEY]

    def apply(self, db, c, who, ctx):
        cur = copy.deepcopy(LAYOUT.get(db)["layout"])
        if isinstance(c.get("layout"), dict):
            new = c["layout"]
        elif isinstance(c.get("merge"), dict):
            new = cur
            for k, v in c["merge"].items():
                if k == "home" and isinstance(v, dict):
                    new["home"] = {**new["home"], **v}
                elif k == "more" and isinstance(v, dict):
                    new["more"] = {**new["more"], **v}
                elif k in ("nav",):
                    new[k] = v
                elif k == "screens" and isinstance(v, dict):
                    sc = dict(new.get("screens") or {})
                    sc.update(v)  # a screen given here replaces that screen's rules; others stay
                    new["screens"] = sc
                else:
                    raise PatchError(f"merge: неизвестная часть «{k}» (nav, home, more, screens)")
        else:
            raise PatchError("нужно layout (вся раскладка) или merge (часть: nav / home / more)")
        LAYOUT.save(db, LAYOUT.validate(new), who, "ui_layout_patch")

    def ids(self, db):
        return [("*", "Главное меню: нижняя панель, главный экран, «Ещё»")]

    def export(self, db, id_):
        return [{"type": "ui_layout", "layout": LAYOUT.get(db)["layout"]}]

    def doc(self, db):
        targets = "; ".join(f"{k} — {v[0]}{' (ещё не работает: только плитка «скоро» в «Ещё»)' if v[2] == 'locked' else ''}"
                            for k, v in LAYOUT.TARGETS.items())
        blocks = "; ".join(f"{k} — {v}" for k, v in LAYOUT.BLOCKS.items())
        return f"""Изменение `{{"type": "ui_layout", "layout": {{nav, home, more}}}}` (вся раскладка) или
`{{"type": "ui_layout", "merge": {{"home": {{"left": […]}}}}}}` (только часть).
- Кнопка: {{"id": "<действие>", "label": "подпись до 20 символов", "icon": "<иконка>", "hidden": false}}; у больших кнопок
  ещё "color": "#RRGGBB" и "ratio": 0.5…3 (ширина).
- nav — нижняя панель (2–7 кнопок разделов; «home» и «more» обязательны и не скрываются).
- home.blocks — порядок и видимость блоков: {blocks} (каждый блок ровно один раз).
- home.left / home.right — боковые колонки (до 7 кнопок, без повторов между колонками); home.actions — большие кнопки (1–4).
- more.columns — 2, 3 или 4; more.groups — до 10 групп {{"title": "до 32 символов", "items": [кнопки, до 12]}}.
- Действия (id): {targets}.
- Иконки: {", ".join(LAYOUT.ICONS)}.
- screens — правила для ЛЮБОГО экрана игры: {{"<экран>": {{"rules": [{{"key": "текст элемента как в игре (без цифр)",
  "kind": "button|label", "label": "новая подпись до 40 (или пусто)", "hidden": false, "color": "#RRGGBB или пусто",
  "action": "куда ведёт кнопка: id действия из списка выше, \"none\" — выключить, пусто — как в игре",
  "move": -20…20 (сдвиг среди соседних)}}]}}}}. В merge экран из screens целиком заменяет правила этого экрана.
- Экраны: {"; ".join(f"{k} — {v}" for k, v in LAYOUT.SCREEN_IDS.items())}.
- home.tree — ПОЛНАЯ структура главного экрана (игра 0.7.8+; если задана, заменяет blocks/left/right/actions).
  Корень — {{"type": "vbox", "children": [...]}}. Контейнеры: {", ".join(f"{k} ({v})" for k, v in LAYOUT.CONTAINERS.items())};
  поля контейнера: children, sep 0…80 (отступ, px), align start|center|end, min_w 0…1080, columns 1…6 (grid), expand, ratio 0.2…5, hidden.
  Элементы: {", ".join(f"{k} ({v})" for k, v in LAYOUT.WIDGETS.items())}.
  side/big/tile: {{"type": "side", "id": "<действие>", "label": "…", "icon": "…"}} (big: + "color", "ratio");
  text: {{"type": "text", "text": "до 200", "size": "caption|body|title|h1", "color": "#RRGGBB", "align": "…"}};
  image: {{"type": "image", "path": "ui/home/banner_1.png … banner_4.png", "height": 40…1200}}; spacer: {{"type": "spacer", "size": 0…800}}.
  campaign_strip, squad, daily_strip — не больше одного раза. Всего до 120 элементов, вложенность до 8.
  Заменить только структуру: {{"type": "ui_layout", "merge": {{"home": {{"tree": {{…}}}}}}}}.
- ОБЯЗАТЕЛЬНО должно остаться доступным (иначе админка не примет): {"; ".join(f"{t} — {w}" for t, w in LAYOUT.REQUIRED.values())}.
- Элементы экранов (kind:key), снятые с игры:
{self._elements()}"""

    def _elements(self) -> str:
        idx = LAYOUT.map_index()
        lines = []
        for sid, m in idx.items():
            els = [f"{'b' if e['kind'] == 'button' else 't'}:{e['key'][:40]}" for e in m["elements"]][:60]
            if els:
                lines.append(f"  {sid}: " + "; ".join(els))
        return "\n".join(lines) or "  (карта интерфейса ещё не снята)"


def _sections() -> dict:
    from ..ai import admin as AIA
    return AIA.SECTIONS


class AiSettingsT(T):
    title, obj = "Настройки ИИ-жителей (раздел)", "section"

    def _sec(self, name):
        if name == "director":
            return None
        s = _sections().get(name)
        if s is None:
            raise PatchError(f"нет раздела «{name}» (есть: director, {', '.join(_sections())})")
        return s

    def state(self, db, c):
        name = c.get("section", "")
        if name == "director":
            from ..ai import settings as AS
            return AS.get(db)
        s = _sections().get(name)
        return s.get(db) if s else None

    def keys(self, c):
        name = c.get("section", "")
        if name == "director":
            return ["ai_director"]
        s = _sections().get(name)
        return [s.key] if s else []

    def apply(self, db, c, who, ctx):
        name = _need(c, "section")
        vals = _need(c, "values", dict)
        if name == "director":
            from ..ai import settings as AS
            AS.update(db, vals, who)
            return
        self._sec(name).update(db, vals, who)

    def ids(self, db):
        return [("director", "Director (темп и нагрузка)")] + [(k, k) for k in _sections()]

    def export(self, db, id_):
        names = ["director", *_sections()] if id_ in ("*", "") else [id_]
        return [{"type": "ai_settings", "section": n, "values": self.state(db, {"section": n})} for n in names]

    def doc(self, db):
        from ..ai import settings as AS
        lines = ["Изменение `{\"type\": \"ai_settings\", \"section\": \"<раздел>\", \"values\": {параметр: значение}}` — "
                 "можно указать только изменяемые параметры.",
                 f"- director: mode ({', '.join(AS.MODES)}), " + ", ".join(f"{k} {lo}…{hi}" for k, (lo, hi) in AS.LIMITS.items())]
        for name, s in _sections().items():
            parts = []
            for k, f in s.fields.items():
                nm = s.names.get(k, "")
                rng = f"{f[1]}…{f[2]}" if f[0] == "int" else ("да/нет (true/false)" if f[0] == "bool" else
                      ("одно из: " + ", ".join(map(str, f[1])) if f[0] == "choice" else f"строка до {f[1]}"))
                parts.append(f"{k} ({rng}{'; ' + nm if nm else ''})")
            lines.append(f"- {name}: " + "; ".join(parts))
        lines.append("- Ключи внешних языковых моделей патчем не задаются.")
        return "\n".join(lines)


class AiSwitchesT(T):
    title, obj = "Переключатели ИИ (где участвуют)", ""

    def state(self, db, c):
        from ..social.ai.control import global_switches
        return global_switches(db)

    def keys(self, c):
        return ["ai_switches"]

    def apply(self, db, c, who, ctx):
        from ..social.ai.control import GLOBAL_DEFAULT, set_global
        vals = _need(c, "values", dict)
        bad = [k for k in vals if k not in GLOBAL_DEFAULT]
        if bad or any(not isinstance(v, bool) for v in vals.values()):
            raise PatchError(f"переключатели: {', '.join(GLOBAL_DEFAULT)}; значения true/false")
        set_global(db, vals, who)

    def ids(self, db):
        return [("*", "Все переключатели")]

    def export(self, db, id_):
        return [{"type": "ai_switches", "values": self.state(db, {})}]

    def doc(self, db):
        from ..social.ai.control import GLOBAL_NAMES
        return "Изменение `{\"type\": \"ai_switches\", \"values\": {…}}`, значения true/false: " + \
            "; ".join(f"{k} — {v}" for k, v in GLOBAL_NAMES.items())


class ShopT(T):
    title, obj = "Товар магазина", "sku"
    FIELDS = ("price_rub", "discount_pct", "active", "featured", "limit", "ends_at")

    def state(self, db, c):
        p = db.get(ShopProduct, c.get("sku", ""))
        if p is None:
            return None
        return {"name": p.name, **{k: (getattr(p, k).isoformat() if hasattr(getattr(p, k), "isoformat") else getattr(p, k))
                                   for k in self.FIELDS}}

    def apply(self, db, c, who, ctx):
        from ..modules import admin as ADM
        sku = _need(c, "sku")
        f = {k: v for k, v in (c.get("fields") or {}).items()}
        bad = [k for k in f if k not in self.FIELDS]
        if bad:
            raise PatchError(f"неизвестные поля товара: {', '.join(bad)} (можно: {', '.join(self.FIELDS)})")
        ctx["shop_before"].setdefault(sku, self.state(db, c))
        ADM.patch_product(sku, ADM.ProductPatch(**f, reason=str(c.get("reason", "ZIP-патч"))[:200]), who, db)

    def ids(self, db):
        from ..monetization import catalog
        catalog.seed(db)
        return [(p.sku, f"{p.section} · {p.name}") for p in db.scalars(select(ShopProduct).order_by(ShopProduct.section, ShopProduct.sku))]

    def export(self, db, id_):
        from ..monetization import catalog
        catalog.seed(db)
        q = select(ShopProduct).order_by(ShopProduct.section, ShopProduct.sku)
        if id_ not in ("*", ""):
            q = q.where(ShopProduct.sku == id_)
        out = []
        for p in db.scalars(q):
            st = self.state(db, {"sku": p.sku})
            st.pop("name")
            out.append({"type": "shop_product", "sku": p.sku, "name": p.name, "fields": st})
        return out

    def doc(self, db):
        return """Изменение `{"type": "shop_product", "sku": "<товар>", "fields": {…}, "reason": "зачем"}`.
- price_rub — цена в копейках (100 = 1 ₽; от 100 до 10 000 000), discount_pct 0…максимум скидки магазина,
  active (true/false — продаётся ли), featured (число — порядок в витрине), limit {"period": "day|week|month|ever", "count": N},
  ends_at — дата окончания ISO 8601 или null.
- Новые товары патчем не создаются; реальные платежи этим не включаются (тестовый режим)."""


class ArtT(T):
    title, obj = "Графика: картинка или 3D-модель слота", "path"

    def state(self, db, c):
        from ..admin_web import art
        m = art.index()["files"].get(c.get("path", ""))
        return {k: v for k, v in (m or {}).items() if k in ("format", "width", "height", "size", "scale", "anims")} or None

    def apply(self, db, c, who, ctx):
        from ..admin_web import art
        path = _need(c, "path")
        f = _need(c, "file")
        data = ctx["files"].get(f)
        if data is None:
            raise PatchError(f"в архиве нет файла {f}")
        try:
            meta = art.check(path, data)
        except ValueError as e:
            raise PatchError(str(e))
        if meta["format"] == "glb" and ("scale" in c or "anims" in c):
            sc = float(c.get("scale", 1.0))
            if not 0.05 <= sc <= 20:
                raise PatchError("scale 0.05…20")
        ctx["art"].append({"path": path, "data": data, "scale": c.get("scale"), "anims": c.get("anims")})
        ctx["art_after"][path] = meta

    def ids(self, db):
        from ..admin_web import art
        return [(s["path"], f"{sec['title']} · {s.get('title', s['path'])}") for sec in art.catalog() for s in sec["slots"]]

    def export(self, db, id_):
        from ..admin_web import art
        paths = [p for p, _ in self.ids(db)] if id_ in ("*", "") else [id_]
        return [{"type": "art", "path": p, "file": "files/" + p.replace("/", "__")} for p in paths]

    def doc(self, db):
        return """Изменение `{"type": "art", "path": "<слот>", "file": "files/<имя файла в архиве>"}` (+ для 3D-моделей:
"scale": 0.05…20, "anims": {"idle": "…", "attack": "…", "hit": "…", "death": "…", "walk": "…"}).
- Файл кладётся в архив (папка files/). PNG или JPEG (размер в пикселях — как указано для слота; где нужен прозрачный
  фон — только PNG), до 8 МБ; 3D-модель — GLB (binary glTF 2.0) до 40 МБ.
- После применения графика попадает в раздел «Графика»; игроки увидят её после «Опубликовать» (или галочки
  «Сразу опубликовать графику» при загрузке патча)."""

    def slot_doc(self, path: str) -> str:
        from ..admin_web import art
        s = art.slot_info(path) or {}
        if not s:
            return ""
        if s.get("model"):
            return f"Слот `{path}`: 3D-модель GLB. Где видна: {s.get('where', '')}.\nПромпт для генерации: {s.get('prompt', '')}"
        return (f"Слот `{path}`: {s.get('size', '')} px, {'PNG с прозрачным фоном' if s.get('alpha') else 'PNG или JPEG'}. "
                f"Где виден: {s.get('where', '')}.\nПромпт для генерации картинки: {s.get('prompt', '')}\nСовет: {s.get('advice', '')}")


TYPES: dict[str, T] = {"hero": HeroT(), "region": RegionT(), "node": NodeT(), "node_order": NodeOrderT(), "map": MapT(),
                       "ui_layout": LayoutT(), "ai_settings": AiSettingsT(), "ai_switches": AiSwitchesT(),
                       "shop_product": ShopT(), "art": ArtT()}


# ------------------------------------------------------------------ check / apply
def _new_ctx(files: dict) -> dict:
    return {"files": files, "created": {}, "art": [], "art_after": {}, "shop_before": {}}


def _run(db: Session, doc: dict, files: dict, who: str, dry: bool) -> tuple[list[dict], dict]:
    """Applies the changes one by one in ONE transaction (no savepoints: SQLite would commit on release).
    Apply mode stops at the first error (the caller rolls everything back). Dry-run mode keeps going: after an error
    it rolls back and replays the successful changes, so every change gets its own verdict."""
    ctx = _new_ctx(files)
    tx = _Tx(db)
    report, done = [], []
    for i, c in enumerate(doc["changes"], 1):
        t = TYPES[c["type"]]
        item = {"n": i, "type": c["type"], "title": t.title, "object": t.label(c), "ok": True, "error": None, "diff": []}
        try:
            before = t.state(db, c)
            t.apply(tx, c, who, ctx)
            db.flush()
            after = ctx["art_after"].get(c.get("path")) if c["type"] == "art" else t.state(db, c)
            item["new"] = before is None
            item["diff"] = diff(before, after)
            done.append(c)
        except Exception as e:  # editor validation (GameError), patch format, pydantic models of the editors…
            item["ok"] = False
            item["error"] = _gerr(e) if isinstance(e, (GameError, PatchError, ValueError)) else f"{type(e).__name__}: {e}"[:300]
            report.append(item)
            if not dry:
                return report, ctx
            db.rollback()
            ctx = _new_ctx(files)
            for prev in done:  # restore the state of the successful changes before checking the next one
                TYPES[prev["type"]].apply(tx, prev, who, ctx)
                db.flush()
            continue
        report.append(item)
    return report, ctx


def check(db: Session, data: bytes, who: str) -> dict:
    doc, files = read(data)
    try:
        report, _ = _run(db, doc, files, who, dry=True)
    finally:
        db.rollback()  # a dry run never writes
    used = {c.get("file") for c in doc["changes"] if c.get("type") == "art"}
    return {"title": doc.get("title", ""), "description": doc.get("description", ""), "author": doc.get("author", ""),
            "ok": all(r["ok"] for r in report), "changes": report,
            "unused_files": sorted(set(files) - used - {"AI_TASK.md", "README.md", "README.txt"})}


def _patches_dir() -> Path:
    p = get_settings().content_store_path / "patches"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _snapshot(db: Session, doc: dict) -> dict:
    keys = sorted({k for c in doc["changes"] for k in TYPES[c["type"]].keys(c)})
    snap = {}
    for k in keys:
        if k == LAYOUT.KEY:
            snap[k] = LAYOUT.get(db)
        else:
            row = db.get(ServerSetting, k)
            snap[k] = copy.deepcopy(row.value) if row else None
    return snap


def apply(db: Session, data: bytes, who: str, publish_art: bool = False) -> dict:
    doc, files = read(data)
    snap = _snapshot(db, doc)
    report, ctx = _run(db, doc, files, who, dry=False)
    if not all(r["ok"] for r in report):
        db.rollback()
        bad = next(r for r in report if not r["ok"])
        raise GameError("patch_failed", f"Патч не применён (ничего не изменено): изменение №{bad['n']} "
                        f"({bad['title']} {bad['object']}): {bad['error']}", 400)
    pid = utcnow().strftime("%Y%m%d%H%M%S") + "_" + secrets.token_hex(3)
    pdir = _patches_dir() / pid
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "patch.bin").write_bytes(data)
    art_backup = {}
    hist = db.get(ServerSetting, HIST)
    if hist is None:
        hist = ServerSetting(key=HIST, value={"items": []})
        db.add(hist)
    rec = {"id": pid, "at": utcnow().isoformat(), "by": who, "title": str(doc.get("title", ""))[:200],
           "description": str(doc.get("description", ""))[:1000], "author": str(doc.get("author", ""))[:80],
           "types": sorted({c["type"] for c in doc["changes"]}), "count": len(doc["changes"]), "status": "applied",
           "snapshot": snap, "created": ctx["created"], "shop_before": ctx["shop_before"], "art": [a["path"] for a in ctx["art"]]}
    hist.value = {"items": (list((hist.value or {}).get("items", [])) + [rec])[-30:]}
    db.add(AdminAction(admin=who, action="patch_apply", details={"id": pid, "title": rec["title"], "changes": rec["count"],
                                                                    "types": rec["types"]}))
    db.commit()
    published = None
    if ctx["art"]:  # files after the database part succeeded
        from ..admin_web import art
        for a in ctx["art"]:
            old = art.staged_file(a["path"])
            meta = art.index()["files"].get(a["path"])
            if old is not None:
                b = pdir / "art_backup" / a["path"]
                b.parent.mkdir(parents=True, exist_ok=True)
                b.write_bytes(old.read_bytes())
            art_backup[a["path"]] = meta
            art.stage(a["path"], a["data"])
            if a.get("scale") is not None or a.get("anims"):
                m = art.index()["files"][a["path"]]
                art.set_model_settings(a["path"], float(a.get("scale") or m.get("scale", 1.0)), a.get("anims") or m.get("anims", {}))
        (pdir / "art_backup.json").write_text(json.dumps(art_backup, ensure_ascii=False), encoding="utf-8")
        if publish_art:
            from ..admin_web import router as AWR
            published = AWR.art_publish(who, db)
    return {"id": pid, "applied": len(report), "changes": report, "art_published": published}


def history(db: Session) -> list[dict]:
    hist = db.get(ServerSetting, HIST)
    items = list((hist.value or {}).get("items", [])) if hist else []
    return [{k: v for k, v in it.items() if k not in ("snapshot", "shop_before")} for it in reversed(items)]


def rollback(db: Session, pid: str, who: str) -> dict:
    """Restores what the last applied patch changed (only the newest one — older ones would undo later work)."""
    hist = db.get(ServerSetting, HIST)
    items = copy.deepcopy(list((hist.value or {}).get("items", []))) if hist else []  # new objects: JSON change is detected
    live = [it for it in items if it["status"] == "applied"]
    if not live or live[-1]["id"] != pid:
        raise GameError("not_last", "Откатить можно только последний применённый патч", 400)
    rec = live[-1]
    snap = rec["snapshot"]
    for k, v in snap.items():
        if k == OV.KEY:
            OV.save(db, v or {}, who, "patch_rollback", {"patch": pid})
            OV._restore_static(db)
            OV.apply(db)
        elif k == LAYOUT.KEY:
            LAYOUT.save(db, v["layout"] if v and v.get("version") else None, who, "ui_layout_patch_rollback")
        else:
            row = db.get(ServerSetting, k)
            if v is None:
                if row is not None:
                    db.delete(row)
            else:
                if row is None:
                    row = ServerSetting(key=k, value={})
                    db.add(row)
                row.value = v
    ov = OV.get(db)
    for code in rec.get("created", {}).get("heroes", []):  # heroes the patch created: removed unless someone owns them
        if code not in ov["heroes"] and not db.scalar(select(func.count()).select_from(PlayerHero).where(PlayerHero.hero_code == code)):
            h = db.get(Hero, code)
            if h is not None:
                db.delete(h)
    for code in rec.get("created", {}).get("nodes", []):
        if code not in ov["nodes"] and not db.scalar(select(func.count()).select_from(PlayerCampaignProgress)
                                                    .where(PlayerCampaignProgress.node_code == code)):
            n = db.get(CampaignNode, code)
            if n is not None:
                db.delete(n)
    db.flush()
    for code in rec.get("created", {}).get("regions", []):
        if code not in ov["regions"] and not db.scalar(select(func.count()).select_from(CampaignNode).where(CampaignNode.region_code == code)):
            r = db.get(CampaignRegion, code)
            if r is not None:
                db.delete(r)
    from ..monetization import catalog
    for sku, before in (rec.get("shop_before") or {}).items():
        p = db.get(ShopProduct, sku)
        if p is None or before is None:
            continue
        from datetime import datetime
        for f in ShopT.FIELDS:
            val = before.get(f)
            if f == "ends_at" and isinstance(val, str):
                val = datetime.fromisoformat(val)
            if getattr(p, f) != val:
                catalog.log_change(db, sku, f, None, before.get(f), f"admin:{who}", f"откат патча {pid}")
                setattr(p, f, val)
    rec["status"] = "rolled_back"
    rec["rolled_back_at"] = utcnow().isoformat()
    hist.value = {"items": [rec if it["id"] == pid else it for it in items]}
    db.add(AdminAction(admin=who, action="patch_rollback", details={"id": pid}))
    db.commit()
    if rec.get("art"):
        from ..admin_web import art
        pdir = _patches_dir() / pid
        backup = json.loads((pdir / "art_backup.json").read_text(encoding="utf-8")) if (pdir / "art_backup.json").exists() else {}
        for path in rec["art"]:
            b = pdir / "art_backup" / path
            if backup.get(path) and b.exists():
                art.stage(path, b.read_bytes())
                m = backup[path]
                if m.get("format") == "glb":
                    art.set_model_settings(path, float(m.get("scale", 1.0)), m.get("anims") or {})
            else:
                art.unstage(path)
    return {"ok": True, "id": pid}


# ------------------------------------------------------------------ AI task templates
GENERAL = f"""## Формат patch.json
```json
{{
  "format": "{FORMAT}",
  "title": "Коротко: что делает патч",
  "description": "Подробнее: что и зачем изменено",
  "author": "название ИИ (Gemini / Claude / ChatGPT / Grok)",
  "changes": [ {{"type": "…", …}} ]
}}
```
## Правила
1. Меняй только то, что просит задание. Неизменённые поля можно не писать — они останутся как есть.
2. Не меняй коды существующих объектов (code, sku, path, section). Новый объект — новый уникальный код.
3. Строго соблюдай допустимые значения и диапазоны ниже — иначе админка не примет патч (она проверяет каждое поле).
4. Только данные: никакого кода, скриптов, SQL, ссылок на внешние файлы.
5. Ответ: ZIP-архив `uralia_patch.zip`, в корне `patch.json` (картинки и модели — в папке `files/`).
   Если не можешь создать файл — выведи только содержимое patch.json одним блоком ```json — его вставят в админку.
6. После патча кратко перечисли, что изменено и почему (для владельца игры).
"""


def task(db: Session, type_: str, id_: str) -> dict:
    """Template for an outside AI: current state as a ready patch + field rules + the owner's wish placeholder."""
    t = TYPES.get(type_)
    if t is None:
        raise GameError("not_found", "Неизвестная настройка", 404)
    changes = t.export(db, id_ or "*")
    if not changes:
        raise GameError("not_found", "Объект не найден", 404)
    patch = {"format": FORMAT, "title": "", "description": "", "author": "", "changes": changes}
    extra = t.slot_doc(id_) if isinstance(t, ArtT) and id_ not in ("*", "") else ""
    name = dict(t.ids(db)).get(id_, "все" if id_ in ("*", "") else id_)
    text = f"""# Задание для ИИ: патч для игры URALIA — {t.title} ({name})

Ты помогаешь владельцу мобильной RPG «URALIA: Дыхание предков» (Южный Урал, башкирские легенды) менять настройки игры.
Изменения загружаются в админ-панель ZIP-патчем; админка проверяет каждое поле и показывает владельцу, что изменится.

## Что нужно сделать
{{{{WISH}}}}

{GENERAL}
## Поля этой настройки ({t.title})
{t.doc(db)}
{extra}

## Текущее состояние (исходный патч — измени его по заданию)
```json
{json.dumps(patch, ensure_ascii=False, indent=1)}
```
"""
    return {"type": type_, "id": id_, "name": name, "title": t.title, "prompt": text, "patch": patch}


def template_zip(db: Session, type_: str, id_: str, wish: str = "") -> bytes:
    tk = task(db, type_, id_)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("patch.json", json.dumps(tk["patch"], ensure_ascii=False, indent=1))
        z.writestr("AI_TASK.md", tk["prompt"].replace("{{WISH}}", wish.strip() or "(опишите здесь, что вы хотите изменить)"))
        if type_ == "art" and id_ not in ("*", ""):
            from ..admin_web import art
            f = art.staged_file(id_)
            if f is not None and f.stat().st_size <= 8 * 1024 * 1024:
                z.writestr("files/" + id_.replace("/", "__") + "." + (art.index()["files"][id_].get("format") or "png").replace("jpg", "jpg"),
                           f.read_bytes())
    return buf.getvalue()


# ------------------------------------------------------------------ API
router = APIRouter(prefix="/admin/api/game/patches", tags=["game-editor"])


@router.get("/types")
def types(who: str = Depends(admin)):
    return {"types": [{"type": k, "title": t.title} for k, t in TYPES.items()], "format": FORMAT}


@router.get("/targets")
def targets(type: str, who: str = Depends(admin), db: Session = Depends(get_db)):
    t = TYPES.get(type)
    if t is None:
        raise GameError("not_found", "Неизвестная настройка", 404)
    ids = t.ids(db)
    multi = [] if len(ids) == 1 and ids[0][0] == "*" else [{"id": "*", "name": "— все сразу —"}]
    if type == "node":
        multi += [{"id": "region:" + r.code, "name": f"— все этапы главы «{r.name}» —"}
                  for r in db.scalars(select(CampaignRegion).order_by(CampaignRegion.order))]
    return {"targets": multi + [{"id": i, "name": n} for i, n in ids]}


@router.get("/task")
def get_task(type: str, id: str = "*", who: str = Depends(admin), db: Session = Depends(get_db)):
    out = task(db, type, id)
    db.rollback()  # shop seeding inside export must not leave a half transaction
    return out


@router.get("/template")
def get_template(type: str, id: str = "*", wish: str = Query("", max_length=4000), who: str = Depends(admin),
                 db: Session = Depends(get_db)):
    data = template_zip(db, type, id, wish)
    safe = re.sub(r"[^a-z0-9_]+", "_", f"{type}_{id}".lower()).strip("_")[:60]
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="uralia_patch_template_{safe}.zip"'})


async def _body(request: Request) -> bytes:
    data = await request.body()
    if not data:
        raise GameError("empty", "Пустой файл", 400)
    if len(data) > MAX_ZIP:
        raise GameError("too_big", "Патч больше 60 МБ", 400)
    return data


@router.post("/check")
async def post_check(request: Request, who: str = Depends(admin), db: Session = Depends(get_db)):
    try:
        return check(db, await _body(request), who)
    except PatchError as e:
        raise GameError("bad_patch", str(e), 400)


@router.post("/apply")
async def post_apply(request: Request, publish_art: bool = Query(False), who: str = Depends(admin),
                     db: Session = Depends(get_db)):
    try:
        return apply(db, await _body(request), who, publish_art)
    except PatchError as e:
        raise GameError("bad_patch", str(e), 400)


@router.get("")
def get_history(who: str = Depends(admin), db: Session = Depends(get_db)):
    return {"items": history(db)}


class RollbackIn(BaseModel):
    id: str


@router.post("/rollback")
def post_rollback(body: RollbackIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    return rollback(db, body.id, who)


@router.get("/{pid}/file")
def patch_file(pid: str, who: str = Depends(admin)):
    if not re.fullmatch(r"[0-9]{14}_[0-9a-f]{6}", pid):
        raise GameError("not_found", "Нет такого патча", 404)
    f = _patches_dir() / pid / "patch.bin"
    if not f.exists():
        raise GameError("not_found", "Файл патча не сохранён", 404)
    data = f.read_bytes()
    zipped = data[:2] == b"PK"
    return Response(data, media_type="application/zip" if zipped else "application/json",
                    headers={"Content-Disposition": f'attachment; filename="uralia_patch_{pid}.{"zip" if zipped else "json"}"'})
