"""Regression tests for the bootstrap admin/admin credential lifecycle.

The bug these pin down: signing in with the shipped default used to CLEAR
`must_change_password` on the account. That made the login path a write path,
so the answer depended on how many times the account had signed in before
rather than on what the credential actually was. Everything here is phrased as
"what must be true on the Nth login", because that is exactly the axis the old
code was wrong on.

Each test gets its own temp state directory and its own SQLite file, so the
bootstrap runs for real (it only fires on a genuinely empty users table) and
nothing depends on the developer's own state/users.db.
"""

import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"
# Must clear config.MIN_PASSWORD_LENGTH (8) - every password-setting route
# enforces it, which is also why no admin-chosen password can ever collide
# with the 5-character built-in default.
NEW_PASSWORD = "S3ntinel!2026"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A backend on a throwaway state directory, booted through lifespan.

    services.config reads os.environ at import time, so the environment has to
    be set before the modules are (re)imported - hence the purge below rather
    than a plain `import services.main`.
    """
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    monkeypatch.setenv("STATE_DIR", str(state_dir))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AUTH_USER_STORE_URL", f"sqlite:///{(state_dir / 'users.db').as_posix()}")
    monkeypatch.setenv("AUTH_BACKEND", "db")
    # The floor config.validate_runtime_config() accepts, to keep the bcrypt
    # work in these tests (many logins, each one hashing) down to seconds.
    monkeypatch.setenv("BCRYPT_ROUNDS", "10")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("AUTO_INGEST_ENABLED", "false")
    # Empty, not unset: this is what selects the built-in default pair and so
    # the whole default-credential code path under test.
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", DEFAULT_USERNAME)

    for name in [m for m in sys.modules if m == "services" or m.startswith("services.")]:
        del sys.modules[name]

    main = importlib.import_module("services.main")
    with TestClient(main.app) as c:
        yield c


def login(client, password, username=DEFAULT_USERNAME):
    return client.post("/auth/login", params={"username": username, "password": password})


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_default_password_keeps_working_across_logouts(client):
    """The reported regression: admin/admin must not stop working by itself.

    Six sign-ins with no password change in between. The old code passed the
    first and could only ever have differed from the second onwards, so a
    single repeat is the whole test - the rest guard against anything that
    degrades on a later login instead.
    """
    for attempt in range(1, 7):
        res = login(client, DEFAULT_PASSWORD)
        assert res.status_code == 200, f"login #{attempt} failed: {res.status_code} {res.text}"
        assert res.json()["username"] == DEFAULT_USERNAME


def test_default_password_prompt_is_soft_and_repeats(client):
    """Still-on-the-default is a prompt every time, never a lock.

    `default_password_prompt` telling the UI to offer "Change now / Remind
    later" is only honest if it survives the reminder being dismissed - the
    old code raised it once and never again, because the flag it derived from
    had been spent on the first login.
    """
    for attempt in range(1, 4):
        body = login(client, DEFAULT_PASSWORD).json()
        assert body["default_password_prompt"] is True, f"prompt missing on login #{attempt}"
        assert body["must_change_password"] is False, f"hard lock on login #{attempt}"
        assert body["default_password_message"]


def test_login_does_not_mutate_the_account(client):
    """A login must change no part of the credential or its policy flag.

    Reads the stored row through the admin API (which reports the raw column,
    unlike /auth/me) before and after, so this fails if anything reintroduces
    a write on the login path - not just the specific write that was removed.
    """
    token = login(client, DEFAULT_PASSWORD).json()["access_token"]

    def stored_admin():
        users = client.get("/admin/users", headers=auth(token)).json()["users"]
        row = next(u for u in users if u["username"] == DEFAULT_USERNAME)
        # last_login_at is deliberately excluded: stamping it is bookkeeping
        # for the admin console, not part of the credential.
        return {k: v for k, v in row.items() if k != "last_login_at"}

    before = stored_admin()
    assert before["must_change_password"] is True, (
        "bootstrap admin should still carry the forced-change flag - the point "
        "is that signing in does not consume it"
    )

    for _ in range(3):
        assert login(client, DEFAULT_PASSWORD).status_code == 200

    assert stored_admin() == before


def test_default_session_can_use_the_app_without_changing_anything(client):
    """"Remind me later" has to actually work.

    The flag stays set in the database now, so this is the test that proves
    credential_change_middleware and /auth/me read the same soft rule the
    login response did. Get it wrong and the account is waved past the login
    screen and then 403'd by every panel it lands on.
    """
    token = login(client, DEFAULT_PASSWORD).json()["access_token"]

    me = client.get("/auth/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["must_change_password"] is False

    # Any route the middleware guards; 401/403 is the failure being tested
    # for, and a 404 from an empty deployment still proves it got through.
    guarded = client.get("/ingestions", headers=auth(token))
    assert guarded.status_code not in (401, 403), guarded.text


def test_old_default_fails_once_the_password_is_actually_changed(client):
    """The other half of the contract: changing the password must close the door."""
    token = login(client, DEFAULT_PASSWORD).json()["access_token"]

    changed = client.post(
        "/auth/account/password",
        headers=auth(token),
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert changed.status_code == 200, changed.text

    stale = login(client, DEFAULT_PASSWORD)
    assert stale.status_code == 401
    assert stale.json()["detail"] == "Invalid credentials"

    for attempt in range(1, 4):
        res = login(client, NEW_PASSWORD)
        assert res.status_code == 200, f"login #{attempt} with the new password failed"
        body = res.json()
        # The default-password prompt has to stop too - the hash no longer
        # matches the shipped default, so there is nothing left to nag about.
        assert body["default_password_prompt"] is False
        assert body["must_change_password"] is False


def test_admin_issued_temporary_password_is_still_a_hard_lock(client):
    """The soft prompt is scoped to the built-in default and nothing else.

    An admin-issued reset with force_change is the case the lock exists for,
    and relaxing it was never part of the fix.
    """
    admin_token = login(client, DEFAULT_PASSWORD).json()["access_token"]

    created = client.post(
        "/admin/users",
        headers=auth(admin_token),
        json={
            "username": "tempuser",
            "password": "Interim!2026",
            "role": "viewer",
            "workspace_id": "default",
            "must_change_password": True,
        },
    )
    assert created.status_code == 200, created.text

    body = login(client, "Interim!2026", username="tempuser").json()
    assert body["must_change_password"] is True, "admin-issued reset must still hard-lock"
    assert body["default_password_prompt"] is False

    locked = client.get("/ingestions", headers=auth(body["access_token"]))
    assert locked.status_code == 403
    assert locked.json()["must_change_password"] is True

    # ...and the escape hatch the lock funnels them into still works.
    assert client.post(
        "/auth/account/password",
        headers=auth(body["access_token"]),
        json={"current_password": "Interim!2026", "new_password": NEW_PASSWORD},
    ).status_code == 200
    assert login(client, NEW_PASSWORD, username="tempuser").json()["must_change_password"] is False


def test_pending_and_disabled_accounts_are_unaffected(client):
    """The security model the fix had to leave alone.

    Both statuses are still refused, and still only explain themselves to a
    caller who already proved they know the password - a wrong password gets
    the generic 401 either way.
    """
    admin_token = login(client, DEFAULT_PASSWORD).json()["access_token"]

    assert client.post(
        "/auth/register",
        json={"username": "waiting", "password": "Interim!2026", "email": ""},
    ).json()["status"] == "pending"

    blocked = login(client, "Interim!2026", username="waiting")
    assert blocked.status_code == 403
    assert "approval" in blocked.json()["detail"].lower()
    assert login(client, "wrong-password", username="waiting").status_code == 401

    assert client.patch(
        "/admin/users/waiting",
        headers=auth(admin_token),
        json={"status": "disabled"},
    ).status_code == 200

    disabled = login(client, "Interim!2026", username="waiting")
    assert disabled.status_code == 403
    assert "disabled" in disabled.json()["detail"].lower()
    assert login(client, "wrong-password", username="waiting").status_code == 401
