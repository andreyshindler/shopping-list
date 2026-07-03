"""FastAPI application entrypoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

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
