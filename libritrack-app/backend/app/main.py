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
@app.on_event("startup")
def ensure_admin_password():
    import sqlite3
    from werkzeug.security import generate_password_hash
    try:
        conn = sqlite3.connect("libritrack.db")
        hashed_pw = generate_password_hash("admin123")
        conn.execute(
            "UPDATE staff SET password = ? WHERE email = ?",
            (hashed_pw, "admin@library.test")
        )
        conn.commit()
        conn.close()
        print("Admin password successfully reset to admin123")
    except Exception as e:
        print("Admin password sync note:", e)
init()
app.include_router(router, prefix="/api")
app.mount("/", StaticFiles(directory=PROJECT_ROOT / "frontend", html=True), name="frontend")
