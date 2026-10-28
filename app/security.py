import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import Depends, Header, HTTPException
from sqlmodel import Session
from .database import get_session
from .models import Token, User

TOKEN_TTL = timedelta(days=7)


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()


def new_salt() -> str:
    return secrets.token_hex(16)


def create_token(session: Session, user_id: int) -> str:
    t = Token(token=secrets.token_urlsafe(32), user_id=user_id)
    session.add(t)
    session.commit()
    return t.token


def current_user(authorization: str = Header(default=""),
                 session: Session = Depends(get_session)) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    tok = session.get(Token, authorization[7:])
    if not tok or datetime.now(timezone.utc) - tok.created_at.replace(tzinfo=timezone.utc) > TOKEN_TTL:
        raise HTTPException(401, "Invalid or expired token")
    return session.get(User, tok.user_id)


def require(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, f"Requires role: {', '.join(roles)}")
        return user
    return dep
