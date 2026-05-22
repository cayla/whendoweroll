"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import settings as settings_module
from app import super_admin_auth
from app.db import init_db
from app.middleware.static_cache import StaticCacheControlMiddleware
from app.routes import admin, index, player, public, super_admin
from app.templates_setup import templates

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    super_admin_auth.bootstrap()
    yield
    super_admin_auth.reset_super_admin_auth()
    settings_module.reset_runtime_settings()


app = FastAPI(title="When Do We Roll", lifespan=lifespan)
app.add_middleware(StaticCacheControlMiddleware)


@app.exception_handler(404)
async def not_found_page(request: Request, _exc: StarletteHTTPException) -> object:
    """HTML error page for unknown routes (links use normal navigation)."""
    return templates.TemplateResponse(
        request,
        "404.html",
        {},
        status_code=404,
    )


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(index.router)
app.include_router(public.router)
app.include_router(admin.router)
app.include_router(player.router)
app.include_router(super_admin.router)
