import os
import bcrypt
import logging
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

load_dotenv()  # Load .env file

logger = logging.getLogger(__name__)

# Read from environment (set in .env)
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable not set")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# ========== USERS WITH HASHED PASSWORDS ==========
# Generated with: bcrypt.hashpw(b'Pass@123', bcrypt.gensalt(rounds=12)).decode()
# Use the hash you generated:
# $2b$12$FozxTuqkAXF0QyX5mH6BNePdFT8XyqFfilXlAAgZ78OkPwyzoTV4W
USERS_HASHED = {
    "aditya": {
        "username": "aditya",
        "password_hash": "$2b$12$FozxTuqkAXF0QyX5mH6BNePdFT8XyqFfilXlAAgZ78OkPwyzoTV4W",
        "role": "qa-engineer"
    },
    "jaydeep": {
        "username": "jaydeep",
        "password_hash": "$2b$12$FozxTuqkAXF0QyX5mH6BNePdFT8XyqFfilXlAAgZ78OkPwyzoTV4W",
        "role": "qa-engineer"
    },
    "ali": {
        "username": "ali",
        "password_hash": "$2b$12$FozxTuqkAXF0QyX5mH6BNePdFT8XyqFfilXlAAgZ78OkPwyzoTV4W",
        "role": "cto"
    },
}

security = HTTPBearer(auto_error=False)


def authenticate_user(username: str, password: str):
    user = USERS_HASHED.get(username.lower())
    if not user:
        return None
    # Verify password against stored hash
    if bcrypt.checkpw(password.encode('utf-8'), user["password_hash"].encode('utf-8')):
        return {"username": username, "role": user["role"]}
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
        if username is None or role is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"username": username, "role": role}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")