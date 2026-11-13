"""App entry point: API under /api, frontend served at /."""
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))  # lets the backend import the ml package

from app.db import init  # noqa: E402
from app.routes import router  # noqa: E402

app = FastAPI(title="LibriTrack-AI")
init()
app.include_router(router, prefix="/api")
app.mount("/", StaticFiles(directory=PROJECT_ROOT / "frontend", html=True), name="frontend")
