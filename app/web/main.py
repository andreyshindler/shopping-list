"""FastAPI application entrypoint."""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _asset_hash(path: str) -> str:
    """Short content hash of a static file, or "0" if it can't be read."""
    try:
        return hashlib.md5((BASE_DIR / "static" / path).read_bytes()).hexdigest()[:8]
    except OSError:
        return "0"


# Hash the static assets once at import — a deploy restarts the process, so a per-process
# cache is enough. StaticFiles sends no Cache-Control, so without this the browser (and
# the aggressive Telegram webview) can keep serving a stale app.js/app.css after a deploy.
_STATIC_HASHES = {name: _asset_hash(name) for name in ("app.css", "app.js")}


def static_url(path: str) -> str:
    """`/static/<path>` with a `?v=<hash>` cache-buster that changes only on edit."""
    version = _STATIC_HASHES.get(path) or _asset_hash(path)
    return f"/static/{path}?v={version}"


templates.env.globals["static_url"] = static_url

# Disable the public API docs/schema — they advertise the full endpoint surface and
# this is a token-gated personal app, not a public API.
app = FastAPI(title="Shopping List", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add baseline security headers.

    ``Referrer-Policy: no-referrer`` matters because access tokens live in the URL —
    it stops them leaking to third parties via the Referer header. No X-Frame-Options
    so the app can still load inside the Telegram Mini App webview.
    """
    response = await call_next(request)
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

from app.web import routes  # noqa: E402  (import after app/templates are defined)

app.include_router(routes.router)
