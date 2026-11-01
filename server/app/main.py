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
from .modules import admin, auth, content, economy, game, health, release, shop
from .admin_web import router as admin_web
from .social.ai import control as ai_control
from .social import (admin_social, arena, chat, events, friends, guilds, moderation, raids, rankings, scheduler,
                     tournaments)

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
              rankings.router, release.router, ai_control.router):
        app.include_router(r, prefix=API)
    app.include_router(health.router)
    app.include_router(admin.router)
    app.include_router(admin.page)
    app.include_router(admin_social.router)
    app.include_router(release.page)
    app.include_router(admin_web.router)
    app.include_router(admin_web.page)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": {"code": "validation_error", "message":
                            "Некорректные данные запроса", "errors": jsonable_encoder(exc.errors()[:5], custom_encoder={Exception: str})}})

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers.setdefault("Cache-Control", "no-store")
        resp.headers["X-Server-Version"] = VERSION
        return resp

    return app


app = create_app()
