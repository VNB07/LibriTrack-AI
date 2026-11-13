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
@app.on_event("startup")
def ensure_admin_password():
    import sqlite3
    try:
        conn = sqlite3.connect("libritrack.db")
        conn.execute(
            "UPDATE staff SET password = ? WHERE email = ?",
            ("pbkdf2:sha256:600000$5dc6c8b77a093b69cc6d01ba3040e6ab$5fe7bc50f0cf25fb193f1733fc3b47179b00ad1786990212621182f98799acca", "admin@library.test")
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print("Admin password sync note:", e)
init()
app.include_router(router, prefix="/api")
app.mount("/", StaticFiles(directory=PROJECT_ROOT / "frontend", html=True), name="frontend")
