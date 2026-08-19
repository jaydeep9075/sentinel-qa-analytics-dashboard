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
        workspace_id=args.workspace or config.AUTH_DEFAULT_WORKSPACE,
        email=args.email,
    )
    print(
        f"Upserted user: {user['username']} role={user['role']} "
        f"workspace={user['workspace_id']} status={user['status']}"
    )
    return 0


def _cmd_set_workspace(store: UserStore, args: argparse.Namespace) -> int:
    user = store.update_user(args.username, workspace_id=args.workspace)
    if user is None:
        print("User not found", file=sys.stderr)
        return 1
    print(f"Moved {args.username} to workspace '{user['workspace_id']}'")
    return 0


def _cmd_approve(store: UserStore, args: argparse.Namespace) -> int:
    """Approve a pending self-service registration."""
    record = store.get_user_record(args.username)
    if record is None:
        print("User not found", file=sys.stderr)
        return 1

    workspace = args.workspace or record.get("requested_workspace") or config.AUTH_DEFAULT_WORKSPACE
    role = args.role or config.AUTH_DEFAULT_ROLE
    user = store.update_user(args.username, role=role, workspace_id=workspace, status="active")
    print(f"Approved {user['username']} role={user['role']} workspace={user['workspace_id']}")
    return 0


def _cmd_delete_user(store: UserStore, args: argparse.Namespace) -> int:
    if store.count_admins(exclude=args.username) == 0:
        record = store.get_user_record(args.username)
        if record and str(record.get("role", "")).lower() in {"admin", "cto"}:
            print("Refusing to delete the only active administrator", file=sys.stderr)
            return 1
    if not store.delete_user(args.username):
        print("User not found", file=sys.stderr)
        return 1
    print(f"Deleted {args.username}")
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
    width = max(len(u["username"]) for u in users)
    for u in users:
        requested = (
            f"  (requested: {u['requested_workspace']})"
            if u["status"] == "pending" and u["requested_workspace"]
            else ""
        )
        print(
            f"{u['username']:<{width}}  status={u['status']:<8} "
            f"role={u['role'] or '-':<12} workspace={u['workspace_id'] or '-'}{requested}"
        )

    pending = [u for u in users if u["status"] == "pending"]
    if pending:
        print(
            f"\n{len(pending)} account(s) awaiting approval. Approve with:\n"
            f"  python -m services.admin_users approve --username <name> "
            f"--workspace <workspace> --role sdet"
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
    p_create.add_argument("--workspace", required=False, help="Workspace the user belongs to")
    p_create.add_argument("--email", required=False)
    p_create.set_defaults(func=_cmd_create_user)

    p_ws = sub.add_parser("set-workspace", help="Move a user to another workspace")
    p_ws.add_argument("--username", required=True)
    p_ws.add_argument("--workspace", required=True)
    p_ws.set_defaults(func=_cmd_set_workspace)

    p_approve = sub.add_parser("approve", help="Approve a pending registration")
    p_approve.add_argument("--username", required=True)
    p_approve.add_argument("--workspace", required=False, help="Defaults to what they requested")
    p_approve.add_argument("--role", required=False, help=f"Defaults to AUTH_DEFAULT_ROLE")
    p_approve.set_defaults(func=_cmd_approve)

    p_del = sub.add_parser("delete-user", help="Permanently delete a user")
    p_del.add_argument("--username", required=True)
    p_del.set_defaults(func=_cmd_delete_user)

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
    # Every subcommand touches columns added after the first release, so the
    # in-place migration has to have run - otherwise the CLI is the one path
    # that hits the old schema (the API gets migrated via startup).
    store.init_db()
    return args.func(store, args)


if __name__ == "__main__":
    raise SystemExit(main())
