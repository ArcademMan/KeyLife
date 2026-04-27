"""FastAPI server: read-only HTTP layer + static frontend.

Bound to loopback (127.0.0.1) only. No auth: the daemon already runs with the
user's privileges and the data never leaves the machine.

When run via `python -m app --serve`, the app's lifespan starts/stops
KeyLifeDaemon alongside uvicorn so a single process owns both the hook and
the API.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.paths import PROJECT_ROOT
from app.service.daemon import KeyLifeDaemon

from .routes import router

log = logging.getLogger(__name__)

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


def _mount_frontend(app: FastAPI) -> None:
    if not FRONTEND_DIST.is_dir():
        log.warning("frontend/dist not found; UI will return 404. Run `npm run build` in frontend/.")
        return

    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    index = FRONTEND_DIST / "index.html"

    @app.get("/", include_in_schema=False)
    def _index() -> FileResponse:
        return FileResponse(index)

    # SPA fallback: any non-API path returns index.html so vue-router handles it.
    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa(full_path: str) -> FileResponse:
        candidate = FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)


def build_app(daemon: KeyLifeDaemon | None = None) -> FastAPI:
    """Build the FastAPI app.

    If `daemon` is None, a fresh daemon is created and managed by the app
    lifespan. Pass an existing daemon to share it with another runtime
    (e.g. embedded inside the Qt UI).
    """
    owned = daemon is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        d = daemon if daemon is not None else KeyLifeDaemon()
        if owned:
            d.start()
        app.state.aggregator = d.aggregator
        try:
            yield
        finally:
            if owned:
                d.stop()

    app = FastAPI(
        title="KeyLife API",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.exception_handler(Exception)
    async def _log_unhandled(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": f"{type(exc).__name__}: {exc}"},
        )

    app.include_router(router)
    _mount_frontend(app)
    return app


def run() -> None:
    """Console entry point: start daemon + serve API on loopback."""
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    )
    settings = get_settings()
    app = build_app()
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
        access_log=True,
    )
