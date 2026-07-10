import os
import json
import bcrypt
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from jose import JWTError, jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from . import config
from .user_store import UserStore

load_dotenv()  # Load .env file

logger = logging.getLogger(__name__)

# Read from environment (set in .env)
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable not set")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

_user_store = UserStore(config.AUTH_USER_STORE_URL)
_auth_store_initialized = False
_memory_users = {}

security = HTTPBearer(auto_error=False)


def _normalize_workspace(workspace_id: Optional[str]) -> str:
    ws = str(workspace_id or "").strip().lower()
    if not ws:
        ws = str(getattr(config, "DEFAULT_WORKSPACE_ID", "default") or "default").strip().lower()
    return ws or "default"


def _hash_password(password: str) -> str:
    rounds = int(config.BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("utf-8")


def _load_seed_users(seed_path: str) -> dict:
    path = Path(seed_path)
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Failed to parse auth seed file '%s': %s", seed_path, exc)
        return {}

    users = data.get("users") if isinstance(data, dict) else data
    if not isinstance(users, list):
        logger.error("Invalid auth seed format in '%s': expected top-level users list", seed_path)
        return {}

    normalized = {}
    for raw in users:
        if not isinstance(raw, dict):
            continue
        username = str(raw.get("username", "")).strip().lower()
        role = str(raw.get("role", "qa-engineer")).strip() or "qa-engineer"
        if not username:
            continue

        password_hash = str(raw.get("password_hash", "")).strip()
        if not password_hash:
            plain_password = str(raw.get("password", "")).strip()
            if not plain_password:
                continue
            password_hash = _hash_password(plain_password)

        normalized[username] = {
            "username": username,
            "password_hash": password_hash,
            "role": role,
        }

    return normalized


def initialize_auth_store() -> None:
    global _auth_store_initialized
    global _memory_users

    if _auth_store_initialized:
        return

    seed_users = {}
    if config.AUTH_AUTO_SEED_USERS:
        seed_users = _load_seed_users(config.AUTH_SEED_FILE)
        if not seed_users:
            logger.warning(
                "AUTH_AUTO_SEED_USERS is enabled but no valid users found in seed file: %s",
                config.AUTH_SEED_FILE,
            )

    if config.AUTH_BACKEND == "db":
        _user_store.init_db(seed_users=seed_users)
        logger.info("Auth backend initialized: db (%s)", config.AUTH_USER_STORE_URL)
    else:
        _memory_users = seed_users
        logger.info("Auth backend initialized: memory")

    _auth_store_initialized = True


def authenticate_user(username: str, password: str, workspace_id: Optional[str] = None):
    initialize_auth_store()
    uname = str(username or "").strip().lower()

    user = None
    if config.AUTH_BACKEND == "db":
        user = _user_store.get_user(uname)
    else:
        user = _memory_users.get(uname)

    if not user:
        return None

    # Verify password against stored hash
    if bcrypt.checkpw(password.encode('utf-8'), user["password_hash"].encode('utf-8')):
        return {
            "username": user["username"],
            "role": user["role"],
            "workspace_id": _normalize_workspace((user or {}).get("workspace_id") or workspace_id),
        }
    return None


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        workspace_id: str = _normalize_workspace(payload.get("workspace_id"))
        if username is None or role is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"username": username, "role": role, "workspace_id": workspace_id}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")