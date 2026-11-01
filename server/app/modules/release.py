"""APK releases: the client asks whether a newer APK exists; players download it from /download.

The owner publishes a release by copying the APK into the downloads folder and editing release.json
(no rebuild or restart needed):
    {"version": "0.6.0", "min_version": "0.5.0", "file": "uralia-0.6.0.apk",
     "url": null, "title": "...", "notes": ["...", "..."]}
`url` may point to any external download page; when null the server serves `file` itself."""
from __future__ import annotations

import html
import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, HTMLResponse

from ..core.config import get_settings
from ..core.errors import GameError

router = APIRouter(tags=["release"])
page = APIRouter(tags=["release"])

DEFAULT = {"version": "0.6.0", "min_version": "0.1.0", "file": "uralia.apk", "url": None,
           "title": "Онлайн-обновление: чат и жители Уралии",
           "notes": ["Общий, гильдейский и личный чат с реакциями и жалобами",
                     "Друзья: поиск по ID и имени, рекомендации, подарки и помощь",
                     "ИИ-жители Уралии с метками «ИИ»: общаются, дружат, отвечают в личке",
                     "Окно обновления приложения прямо в игре"]}


def semver(v: str) -> tuple:
    out = []
    for x in str(v).split(".")[:3]:
        try:
            out.append(int("".join(c for c in x if c.isdigit()) or 0))
        except ValueError:
            out.append(0)
    return tuple(out + [0] * (3 - len(out)))


def release() -> dict:
    path = get_settings().downloads_path / "release.json"
    data = dict(DEFAULT)
    if path.exists():
        try:
            data.update(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    try:  # the web admin panel stores the release in the DB; it overrides release.json
        from sqlalchemy.orm import Session
        from ..core.db import get_engine
        from ..models import ServerSetting
        with Session(get_engine()) as db:
            row = db.get(ServerSetting, "release")
            if row and row.value:
                data.update({k: v for k, v in row.value.items() if v is not None or k == "url"})
    except Exception:
        pass
    return data


def _apk_path():
    rel = release()
    f = get_settings().downloads_path / str(rel.get("file") or "uralia.apk")
    return f if f.is_file() and f.suffix == ".apk" and f.resolve().parent == get_settings().downloads_path.resolve() else None


def _download_url(request: Request) -> str | None:
    rel = release()
    if rel.get("url"):
        return rel["url"]
    return str(request.base_url).rstrip("/") + "/download" if _apk_path() else None


@router.get("/client/release")
def client_release(request: Request, version: str = Query("0.0.0", max_length=20)):
    rel = release()
    url = _download_url(request)
    newer = semver(rel["version"]) > semver(version)
    return {"latest": rel["version"], "min_version": rel["min_version"], "title": rel.get("title", ""),
            "notes": rel.get("notes", []), "url": url,
            "update_available": bool(newer and url), "required": semver(version) < semver(rel["min_version"])}


@page.get("/download", response_class=HTMLResponse)
def download_page(request: Request):
    rel = release()
    apk = _apk_path()
    notes = "".join(f"<li>{html.escape(str(n))}</li>" for n in rel.get("notes", []))
    if rel.get("url") and not apk:
        btn = f'<a class="b" href="{html.escape(rel["url"])}">Перейти к загрузке</a>'
    elif apk:
        size = apk.stat().st_size / 1048576
        btn = f'<a class="b" href="/download/apk">Скачать APK {html.escape(rel["version"])} ({size:.0f} МБ)</a>'
    else:
        btn = "<p>Файл обновления ещё не загружен на сервер.</p>"
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>УРАЛИЯ — загрузка</title>
<style>body{{margin:0;background:#141826;color:#f5f1e6;font-family:system-ui,sans-serif;padding:24px 16px}}
.c{{max-width:560px;margin:auto}}h1{{color:#f4cf7a;margin:0 0 4px}}.v{{color:#b8c3d6}}li{{margin:8px 0}}
.b{{display:block;text-align:center;background:#d9a23f;color:#2b1600;font-weight:700;padding:18px;border-radius:16px;
text-decoration:none;font-size:20px;margin:24px 0}}.n{{color:#b8c3d6;font-size:14px}}</style></head>
<body><div class="c"><h1>УРАЛИЯ: Дыхание предков</h1><div class="v">Версия {html.escape(rel["version"])}</div>
<h3>{html.escape(rel.get("title", ""))}</h3><ul>{notes}</ul>{btn}
<p class="n">После загрузки откройте файл и разрешите установку из этого источника. Прогресс сохраняется на сервере:
если аккаунт привязан к email, вход сохранится и на новом телефоне.</p></div></body></html>"""


@page.get("/download/apk")
def download_apk():
    apk = _apk_path()
    if apk is None:
        raise GameError("not_found", "Файл обновления не загружен", 404)
    return FileResponse(apk, media_type="application/vnd.android.package-archive",
                        filename=f"uralia-{release()['version']}.apk")
