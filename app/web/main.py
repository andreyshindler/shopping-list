"""FastAPI application entrypoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Shopping List")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

from app.web import routes  # noqa: E402  (import after app/templates are defined)

app.include_router(routes.router)
