from datetime import datetime, timedelta, timezone
import jwt
from pwdlib import PasswordHash
from app.core.config import settings

_password_hash = PasswordHash.recommended()

def hash_password(password: str) -> str:
    return _password_hash.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hash.verify(password, password_hash)
    except Exception:
        return False

def create_access_token(subject: str) -> tuple[str, int]:
    expires_seconds = settings.access_token_expire_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {"sub": subject, "iat": now, "exp": now + timedelta(seconds=expires_seconds), "typ": "access"}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm), expires_seconds

def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        subject = payload.get("sub")
        return subject if payload.get("typ") == "access" and isinstance(subject, str) else None
    except jwt.PyJWTError:
        return None
