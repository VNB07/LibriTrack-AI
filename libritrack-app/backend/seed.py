"""Creates the first admin account. Run once: python seed.py"""
import os

from app.db import init, execute, query
from app.security import hash_password

init()
email = os.getenv("LIBRITRACK_ADMIN_EMAIL", "admin@library.test")
password = os.getenv("LIBRITRACK_ADMIN_PASSWORD", "ChangeMe123!")
if query("SELECT id FROM staff WHERE email=?", (email,), one=True):
    print("Admin already exists:", email)
else:
    execute("INSERT INTO staff(email,name,password_hash,role) VALUES(?,?,?,?)",
            (email, "Administrator", hash_password(password), "admin"))
    print("Admin created:", email, "password:", password)
