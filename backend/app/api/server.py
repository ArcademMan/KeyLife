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
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.paths import PROJECT_ROOT
from app.service.daemon import KeyLifeDaemon

from .routes import router

log = logging.getLogger(__name__)

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


class LoopbackHostMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Host header is not a loopback name.

    The API binds to 127.0.0.1 so a remote attacker cannot reach the socket
    directly. They CAN, however, use the user's own browser as a proxy via
    DNS rebinding: a malicious page on `evil.com` lowers its DNS TTL and
    re-resolves the domain to 127.0.0.1; the browser then talks to our
    loopback API while still believing the origin is `evil.com`. The Host
    header in that request is `evil.com`, not `127.0.0.1` — so an explicit
    allowlist closes the vector.
    """

    def __init__(self, app, allowed_hosts: frozenset[str]) -> None:
        super().__init__(app)
        self._allowed = allowed_hosts

    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower()
        hostname = _strip_port(host)
        if hostname not in self._allowed:
            return PlainTextResponse(
                "Forbidden: unexpected Host header",
                status_code=403,
            )
        return await call_next(request)


def _strip_port(host: str) -> str:
    """Return the hostname portion of an HTTP Host header value.

    Handles four shapes:
      - empty
      - hostname            -> as is
      - hostname:port       -> drop port
      - [ipv6]              -> as is (with brackets)
      - [ipv6]:port         -> drop port, keep brackets
    """
    if not host:
        return ""
    if host.startswith("["):
        # Bracketed IPv6: split off any trailing :port after the closing ].
        end = host.find("]")
        if end == -1:
            return host  # malformed; let the allowlist reject it
        return host[: end + 1]
    # Plain host or host:port.
    if host.count(":") == 1:
        return host.rsplit(":", 1)[0]
    # Bare unbracketed IPv6 (e.g. "::1") — no port can be present here per
    # RFC 7230, so return as-is.
    return host


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]", "::1"})


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
    # Resolve and confine inside FRONTEND_DIST: a crafted path like
    # `..%5C..%5Cwindows\win.ini` would otherwise escape the static root and
    # let any caller read process-readable files.
    dist_root = FRONTEND_DIST.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa(full_path: str) -> FileResponse:
        candidate = (FRONTEND_DIST / full_path).resolve()
        try:
            candidate.relative_to(dist_root)
        except ValueError:
            return FileResponse(index)
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

    from app import __version__

    app = FastAPI(
        title="KeyLife API",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(LoopbackHostMiddleware, allowed_hosts=_LOOPBACK_HOSTS)

    @app.exception_handler(Exception)
    async def _log_unhandled(request: Request, exc: Exception):
        # Log the full traceback locally; the client only gets a generic
        # message. Exception text can carry filesystem paths (with the OS
        # username) and SQL fragments — we don't want those in browser
        # devtools or in any logs the user might paste publicly.
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "internal server error"},
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
