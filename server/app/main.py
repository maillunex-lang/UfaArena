"""URALIA backend — modular monolith (FastAPI)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .core.config import get_settings
from .core.db import Base, get_engine, init_engine
from .game.seed import seed_static
from .modules import admin, auth, caravan, content, economy, game, health, hub, release, shop, story
from .admin_web import router as admin_web
from .social.ai import control as ai_control
from .social import (admin_social, alliances, arena, chat, events, friends, guilds, moderation, raids, rankings,
                     scheduler, tournaments)

API = "/api/v1"
VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    init_engine(s.database_url)
    if s.env in ("dev", "test") and s.database_url.startswith("sqlite"):
        Base.metadata.create_all(get_engine())  # Postgres uses Alembic migrations
    with Session(get_engine()) as db:
        seed_static(db)
    task = None
    if scheduler.enabled():
        import asyncio
        task = asyncio.create_task(scheduler.loop())
    yield
    if task:
        task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="URALIA API", version=VERSION, lifespan=lifespan,
                  docs_url="/docs" if get_settings().env != "prod" else None)
    for r in (auth.router, game.router, economy.router, content.router, shop.router, friends.router, guilds.router,
              chat.router, moderation.router, raids.router, arena.router, tournaments.router, events.router,
              rankings.router, release.router, ai_control.router, hub.router, story.router, caravan.router,
              alliances.router):
        app.include_router(r, prefix=API)
    app.include_router(health.router)
    app.include_router(admin.router)
    app.include_router(admin.page)
    app.include_router(admin_social.router)
    app.include_router(release.page)
    app.include_router(admin_web.router)
    app.include_router(admin_web.page)
    from .ai import admin as ai_admin
    app.include_router(ai_admin.router)
    from .game_editor import router as game_editor
    app.include_router(game_editor.router)
    from .game_editor import campaign as campaign_editor
    app.include_router(campaign_editor.router)
    # Web version of the game (Godot Web export, same API on the same origin). Optional: only if exported.
    web = get_settings().web_client_path
    if (web / "index.html").exists():
        from fastapi.staticfiles import StaticFiles
        app.mount("/play", StaticFiles(directory=str(web), html=True), name="play")

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": {"code": "validation_error", "message":
                            "Некорректные данные запроса", "errors": jsonable_encoder(exc.errors()[:5], custom_encoder={Exception: str})}})

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/play/"):
            resp.headers.setdefault("Cache-Control", "public, max-age=600")  # large wasm/pck: short browser cache
        resp.headers.setdefault("Cache-Control", "no-store")
        resp.headers["X-Server-Version"] = VERSION
        return resp

    return app


app = create_app()
