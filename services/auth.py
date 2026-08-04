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

    # Set before bootstrapping: _bootstrap_admin_if_empty() goes through the
    # store, and leaving the flag false here would re-enter this function.
    _auth_store_initialized = True
    _bootstrap_admin_if_empty()


class AuthError(Exception):
    """Login failed for a reason the caller is allowed to be told about.

    Distinct from returning None (bad credentials): "your account is awaiting
    approval" is only ever raised AFTER the password has been verified, so it
    leaks nothing to someone who doesn't already know the password.
    """

    def __init__(self, detail: str, status_code: int = 403):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def authenticate_user(username: str, password: str, workspace_id: Optional[str] = None):
    """Verify credentials and return the account's SERVER-SIDE identity.

    `workspace_id` is accepted and ignored. It used to be honoured, which meant
    a client could name any workspace it liked at login - including one that
    had never been registered anywhere - and the resulting token would carry
    it. The workspace is an authorization decision, so it now comes from the
    user's row and nowhere else. The parameter is kept so the older callers
    and the existing query-string contract don't break.
    """
    initialize_auth_store()
    uname = str(username or "").strip().lower()

    if config.AUTH_BACKEND == "db":
        user = _user_store.get_user(uname)
    else:
        user = _memory_users.get(uname)

    if not user:
        # The account may exist but be pending/disabled, in which case
        # get_user() deliberately returned nothing. Only tell the caller which
        # it is once they've proven they know the password.
        _raise_if_blocked_and_password_matches(uname, password)
        return None

    if not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        return None

    if config.AUTH_BACKEND == "db":
        _user_store.record_login(uname)

    return {
        "username": user["username"],
        "role": user["role"],
        "workspace_id": _normalize_workspace(user.get("workspace_id")),
        "must_change_password": bool(user.get("must_change_password")),
    }


def _raise_if_blocked_and_password_matches(uname: str, password: str) -> None:
    if config.AUTH_BACKEND != "db" or not uname:
        return

    status_value = _user_store.get_login_status(uname)
    if status_value in (None, "active"):
        return

    stored_hash = _user_store.get_password_hash(uname)
    if not stored_hash:
        return
    try:
        if not bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")):
            return
    except ValueError:
        return

    if status_value == "pending":
        raise AuthError(
            "Your account is awaiting administrator approval.", status_code=403
        )
    raise AuthError("This account has been disabled.", status_code=403)


def register_user(
    username: str,
    password: str,
    email: str = "",
    requested_workspace: str = "",
) -> dict:
    """Create a self-service signup as a PENDING account.

    Pending means: the row exists, the password is stored, and login is
    refused until an admin approves it and assigns a workspace. Registration
    therefore grants no access to any data - it only puts a request in a
    queue - which is what makes it safe to expose without an invite system.
    """
    initialize_auth_store()

    if not config.AUTH_ALLOW_SELF_REGISTRATION:
        raise AuthError("Self-service registration is disabled on this deployment.", 403)
    if config.AUTH_BACKEND != "db":
        raise AuthError("Registration requires AUTH_BACKEND=db.", 400)

    uname = str(username or "").strip().lower()
    if len(uname) < 3 or len(uname) > 64:
        raise AuthError("Username must be between 3 and 64 characters.", 400)
    if not all(ch.isalnum() or ch in "._-" for ch in uname):
        raise AuthError("Username may only contain letters, numbers, dot, underscore and hyphen.", 400)
    if len(password or "") < 8:
        raise AuthError("Password must be at least 8 characters.", 400)

    password_hash = _hash_password(password)

    if config.AUTH_AUTO_APPROVE_REGISTRATION:
        # Explicit opt-in for trusted networks: skip the queue entirely.
        try:
            if _user_store.get_user_record(uname) is not None:
                raise AuthError("That username is already taken.", 409)
            record = _user_store.upsert_user(
                username=uname,
                password_hash=password_hash,
                role=config.AUTH_DEFAULT_ROLE,
                workspace_id=config.AUTH_DEFAULT_WORKSPACE,
                email=email,
                status="active",
            )
        except ValueError as exc:
            raise AuthError(str(exc), 409) from exc
        logger.info("Auto-approved registration for '%s'", uname)
        return {"status": "active", "user": record}

    try:
        record = _user_store.create_pending_user(
            username=uname,
            password_hash=password_hash,
            email=email,
            requested_workspace=requested_workspace,
        )
    except ValueError as exc:
        raise AuthError("That username is already taken.", 409) from exc

    logger.info("Registration pending approval for '%s'", uname)
    return {"status": "pending", "user": record}


def _bootstrap_admin_if_empty() -> None:
    """Create the very first admin when the store is empty.

    Only fires on a genuinely empty table, so it can't be used to reset or
    override an existing account - editing BOOTSTRAP_ADMIN_PASSWORD later does
    nothing. Without this, a fresh container has no way in except an exec into
    the container, which is a poor first-run experience for a deployment
    someone else set up.

    Both username and password now default (see config.py) to a known
    "admin"/"admin" pair, so this always fires on a genuinely fresh
    deployment - `docker compose up` with an empty .env produces a login you
    can actually use, the appliance pattern. That is only safe because the
    account it creates cannot do anything except change its own credentials:
    must_change_password is forced on whenever the password in use is still
    the literal built-in default, regardless of
    BOOTSTRAP_ADMIN_FORCE_PASSWORD_CHANGE - that flag only controls whether an
    *explicitly configured* BOOTSTRAP_ADMIN_PASSWORD also forces a change.
    """
    if config.AUTH_BACKEND != "db":
        return
    if not config.BOOTSTRAP_ADMIN_USERNAME or not config.BOOTSTRAP_ADMIN_PASSWORD:
        return
    if _user_store.count_users() > 0:
        return

    is_default_password = config.bootstrap_password_is_default()
    if not is_default_password and len(config.BOOTSTRAP_ADMIN_PASSWORD) < config.MIN_PASSWORD_LENGTH:
        logger.error(
            "BOOTSTRAP_ADMIN_PASSWORD is shorter than %s characters - refusing to bootstrap",
            config.MIN_PASSWORD_LENGTH,
        )
        return

    force_change = is_default_password or config.BOOTSTRAP_ADMIN_FORCE_PASSWORD_CHANGE

    _user_store.upsert_user(
        username=config.BOOTSTRAP_ADMIN_USERNAME,
        password_hash=_hash_password(config.BOOTSTRAP_ADMIN_PASSWORD),
        role="admin",
        workspace_id=config.AUTH_DEFAULT_WORKSPACE,
        status="active",
        must_change_password=force_change,
    )
    if is_default_password:
        logger.warning(
            "Bootstrapped first admin '%s' with the BUILT-IN DEFAULT password. "
            "Sign in with username '%s' and password '%s' - you will be required "
            "to set a real username and password before doing anything else. Set "
            "BOOTSTRAP_ADMIN_USERNAME/BOOTSTRAP_ADMIN_PASSWORD in .env to skip "
            "shipping with the default at all.",
            config.BOOTSTRAP_ADMIN_USERNAME, config.BOOTSTRAP_ADMIN_USERNAME,
            config.BOOTSTRAP_ADMIN_PASSWORD,
        )
    else:
        logger.warning(
            "Bootstrapped first admin '%s'.%s",
            config.BOOTSTRAP_ADMIN_USERNAME,
            " Must change password on first login." if force_change else "",
        )


def get_user_store() -> UserStore:
    initialize_auth_store()
    return _user_store


def verify_password(username: str, password: str) -> bool:
    """Re-check a password for an ALREADY-authenticated session.

    Used by the account-settings endpoints (change own password / username),
    which require the current password even though the caller already holds
    a valid bearer token - the token proves who is asking, not that they
    still know the password, which matters if the session was left open on a
    shared machine. Deliberately bypasses get_user() (the login path, which
    refuses pending/disabled accounts): a must-change-password account is
    exactly the case this has to work for, and it's the ONLY thing that
    account is allowed to do.
    """
    initialize_auth_store()
    uname = str(username or "").strip().lower()
    if not uname or not password:
        return False
    stored_hash = _user_store.get_password_hash(uname)
    if not stored_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except ValueError:
        return False


def change_own_password(username: str, current_password: str, new_password: str) -> None:
    """Self-service password change. Raises AuthError on any failure.

    Clears must_change_password unconditionally on success - this is the
    route that flag exists to force the caller into, so completing it always
    lifts the restriction, regardless of whether an admin or the bootstrap
    process was the one who set it.
    """
    if not verify_password(username, current_password):
        raise AuthError("Current password is incorrect.", 401)
    if len(new_password or "") < config.MIN_PASSWORD_LENGTH:
        raise AuthError(
            f"New password must be at least {config.MIN_PASSWORD_LENGTH} characters.", 400
        )
    if new_password == current_password:
        raise AuthError("New password must be different from the current password.", 400)

    uname = str(username or "").strip().lower()
    _user_store.set_password_hash(uname, _hash_password(new_password))
    _user_store.set_must_change_password(uname, False)


def rename_account(old_username: str, new_username: str) -> dict:
    """Change a user's username everywhere it is stored as a foreign key.

    The username is the primary key in `users`, but it is also embedded (by
    value, not by reference) in two other stores that were built assuming it
    never changes:

      * token_usage - keyed on (workspace_id, user_id, model). A rename that
        only touched `users` would silently reset that person's usage/quota
        history to zero under the new name while the old rows sit there
        attributed to a username nobody can log in as any more.
      * build ownership (owner.json `created_by`) - used by
        build_owner.can_delete() to decide whether THIS user may delete a
        build they created. Left stale, a rename would quietly revoke delete
        rights on every build they'd made before renaming.

    All three moves happen here, in this order, so a caller never has to
    remember the other two when the CLI or the account-settings endpoint
    changes a username.
    """
    from . import token_usage_store, build_owner  # local: avoid import cycle

    store = get_user_store()
    updated = store.rename_user(old_username, new_username)
    if updated is None:
        raise AuthError("User not found", 404)

    token_usage_store.rename_user(old_username, new_username)
    build_owner.rename_creator(old_username, new_username)
    return updated


def change_own_username(current_username: str, current_password: str, new_username: str) -> dict:
    """Self-service username change. Raises AuthError on any failure.

    Same character/length rules as registration (register_user) so a self
    -chosen username can never collide with what the login form or the URL
    path in /admin/users/{username} would reject.
    """
    if not verify_password(current_username, current_password):
        raise AuthError("Current password is incorrect.", 401)

    new_uname = str(new_username or "").strip().lower()
    if len(new_uname) < 3 or len(new_uname) > 64:
        raise AuthError("Username must be between 3 and 64 characters.", 400)
    if not all(ch.isalnum() or ch in "._-" for ch in new_uname):
        raise AuthError("Username may only contain letters, numbers, dot, underscore and hyphen.", 400)

    try:
        return rename_account(current_username, new_uname)
    except ValueError as exc:
        raise AuthError(str(exc), 409) from exc


def hash_password(password: str) -> str:
    return _hash_password(password)


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


ADMIN_ROLES = frozenset({"admin", "cto"})


def is_admin(user: Optional[dict]) -> bool:
    return str((user or {}).get("role") or "").strip().lower() in ADMIN_ROLES


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency for endpoints only administrators may call.

    A dependency rather than an `if` inside each handler: forgetting the check
    then fails closed (the route simply has no admin guard to forget) instead
    of silently shipping an unprotected endpoint.
    """
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Administrator privileges required")
    return current_user