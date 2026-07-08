"""
auth.py
Deliberately simple, fake auth for a hackathon prototype.
Tokens are just "{username}_token" strings — no JWT, no expiry.
"""

from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

from database import User

HARDCODED_USERS = [
    {"username": "mp_sharma", "password": "mp123", "role": "mp", "constituency": "Sample Constituency Delhi"},
    {"username": "mp_verma", "password": "mp456", "role": "mp", "constituency": "Sample Constituency Mumbai"},
    {"username": "citizen1", "password": "citizen123", "role": "citizen", "constituency": None},
    {"username": "citizen2", "password": "citizen456", "role": "citizen", "constituency": None},
    {"username": "guest", "password": "guest", "role": "citizen", "constituency": None},
]


def make_token(username: str) -> str:
    return f"{username}_token"


def username_from_token(token: str) -> str:
    if not token or not token.endswith("_token"):
        return ""
    return token[: -len("_token")]


def login(db: Session, username: str, password: str) -> dict:
    user = db.query(User).filter(User.username == username).first()
    if not user or user.password_hash != password:
        return {"success": False, "error": "Invalid username or password"}

    token = make_token(user.username)
    result = {
        "success": True,
        "role": user.role,
        "username": user.username,
        "token": token,
    }
    if user.role == "mp":
        result["constituency"] = user.constituency
    return result


def verify_token(db: Session, token: str) -> dict:
    username = username_from_token(token)
    if not username:
        return {"valid": False}
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return {"valid": False}
    return {"valid": True, "role": user.role, "username": user.username}


def get_user_from_authorization_header(db: Session, authorization: str | None) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    username = username_from_token(token)
    if not username:
        return None
    return db.query(User).filter(User.username == username).first()


def require_mp(db: Session, authorization: str | None = Header(default=None)) -> User:
    """Dependency-style helper: call this from a route to enforce MP-only access."""
    user = get_user_from_authorization_header(db, authorization)
    if not user or user.role != "mp":
        raise HTTPException(status_code=401, detail="MP authentication required")
    return user
