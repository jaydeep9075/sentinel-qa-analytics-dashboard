import argparse
import getpass
import sys
from typing import Optional

import bcrypt

from . import config
from .user_store import UserStore


def _hash_password(password: str) -> str:
    rounds = int(config.BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("utf-8")


def _prompt_password(provided: Optional[str]) -> str:
    if provided:
        return provided
    value = getpass.getpass("Password: ")
    if not value:
        raise ValueError("password cannot be empty")
    return value


def _cmd_init_db(store: UserStore, args: argparse.Namespace) -> int:
    store.init_db()
    print("Initialized user database")
    return 0


def _cmd_create_user(store: UserStore, args: argparse.Namespace) -> int:
    password = _prompt_password(args.password)
    password_hash = _hash_password(password)
    user = store.upsert_user(
        username=args.username,
        password_hash=password_hash,
        role=args.role,
        is_active=not args.inactive,
    )
    print(f"Upserted user: {user['username']} role={user['role']} active={user['is_active']}")
    return 0


def _cmd_set_role(store: UserStore, args: argparse.Namespace) -> int:
    ok = store.set_role(args.username, args.role)
    if not ok:
        print("User not found", file=sys.stderr)
        return 1
    print(f"Updated role for {args.username} -> {args.role}")
    return 0


def _cmd_reset_password(store: UserStore, args: argparse.Namespace) -> int:
    password = _prompt_password(args.password)
    password_hash = _hash_password(password)
    ok = store.set_password_hash(args.username, password_hash)
    if not ok:
        print("User not found", file=sys.stderr)
        return 1
    print(f"Password reset for {args.username}")
    return 0


def _cmd_set_active(store: UserStore, args: argparse.Namespace) -> int:
    ok = store.set_active(args.username, args.active)
    if not ok:
        print("User not found", file=sys.stderr)
        return 1
    state = "active" if args.active else "inactive"
    print(f"Set {args.username} to {state}")
    return 0


def _cmd_list_users(store: UserStore, args: argparse.Namespace) -> int:
    users = store.list_users()
    if not users:
        print("No users found")
        return 0
    for u in users:
        print(
            f"{u['username']}\trole={u['role']}\tactive={u['is_active']}\tcreated={u['created_at']}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Admin CLI for auth users")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-db", help="Initialize user database schema")
    p_init.set_defaults(func=_cmd_init_db)

    p_create = sub.add_parser("create-user", help="Create or update a user")
    p_create.add_argument("--username", required=True)
    p_create.add_argument("--role", required=True)
    p_create.add_argument("--password", required=False)
    p_create.add_argument("--inactive", action="store_true")
    p_create.set_defaults(func=_cmd_create_user)

    p_role = sub.add_parser("set-role", help="Update user role")
    p_role.add_argument("--username", required=True)
    p_role.add_argument("--role", required=True)
    p_role.set_defaults(func=_cmd_set_role)

    p_pass = sub.add_parser("reset-password", help="Reset user password")
    p_pass.add_argument("--username", required=True)
    p_pass.add_argument("--password", required=False)
    p_pass.set_defaults(func=_cmd_reset_password)

    p_active = sub.add_parser("set-active", help="Set user active or inactive")
    p_active.add_argument("--username", required=True)
    p_active.add_argument("--active", type=lambda x: str(x).lower() in {"1", "true", "yes", "on"}, required=True)
    p_active.set_defaults(func=_cmd_set_active)

    p_list = sub.add_parser("list-users", help="List all users")
    p_list.set_defaults(func=_cmd_list_users)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    store = UserStore(config.AUTH_USER_STORE_URL)
    return args.func(store, args)


if __name__ == "__main__":
    raise SystemExit(main())
