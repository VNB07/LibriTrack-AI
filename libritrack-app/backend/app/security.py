"""Password hashing and login tokens."""
import datetime
import hashlib
import hmac
import os

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

SECRET = os.getenv("LIBRITRACK_SECRET", "dev-only-change-me")
bearer = HTTPBearer()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt.hex() + "$" + digest.hex()


def check_password(password: str, stored: str) -> bool:
    salt_hex, digest_hex = stored.split("$")
    test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 200_000)
    return hmac.compare_digest(test.hex(), digest_hex)


def make_token(staff_id: int, role: str) -> str:
    payload = {
        "sub": str(staff_id),
        "role": role,
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8),
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


def current_staff(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    try:
        data = jwt.decode(creds.credentials, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired. Please log in again.")
    return {"id": int(data["sub"]), "role": data["role"]}


def require_admin(staff: dict = Depends(current_staff)) -> dict:
    if staff["role"] != "admin":
        raise HTTPException(403, "Administrators only")
    return staff
