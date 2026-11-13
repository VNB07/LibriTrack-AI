import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import init, execute, query  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.routes import router  # noqa: E402

app = FastAPI(title="LibriTrack-AI")

init()

if query("SELECT id FROM staff WHERE email=?", ("admin@library.test",), one=True):
    execute(
        "UPDATE staff SET password_hash=? WHERE email=?",
        (hash_password("admin123"), "admin@library.test"),
    )
else:
    execute(
        "INSERT INTO staff(email,name,password_hash,role) VALUES(?,?,?,?)",
        ("admin@library.test", "Administrator", hash_password("admin123"), "admin"),
    )

app.include_router(router, prefix="/api")
app.mount("/", StaticFiles(directory=PROJECT_ROOT / "frontend", html=True), name="frontend")
