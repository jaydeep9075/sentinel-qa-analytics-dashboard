# User Seed and Validation Steps

This guide is the standard process for creating auth users, validating them, and moving forward safely.

## Prerequisites
- Run all commands from repository root:
  - `D:/Ai-testrig/sentinel-qa-analytics-dashboard`
- Activate your venv first.

## 1) Initialize user database (one-time)
```bash
python -m services.admin_users init-db
```
Expected output:
- `Initialized user database`

## 2) Check current users
```bash
python -m services.admin_users list-users
```
If this is first run, expected output:
- `No users found`

## 3) Add users manually (recommended)
Create CTO/admin user:
```bash
python -m services.admin_users create-user --username admin --role cto
```

Create QA user:
```bash
python -m services.admin_users create-user --username qa1 --role qa-engineer
```

You will be prompted for `Password:` for each user.

## 4) Validate users were created
```bash
python -m services.admin_users list-users
```
Expected output should include entries like:
- `admin role=cto active=True`
- `qa1 role=qa-engineer active=True`

## 5) Validate login end-to-end
1. Start backend:
```bash
python -m services.main
```
2. Open API docs: `http://localhost:8000/docs`
3. Test `POST /auth/login` with username/password created above.

## Optional: Seed users from file
Use this only if you want auto-bootstrap from a JSON file.

1. Copy example seed file:
- `auth_seed_users.json.example` -> `auth_seed_users.json`
2. Set env values in `.env`:
```env
AUTH_AUTO_SEED_USERS=true
AUTH_SEED_FILE=./auth_seed_users.json
```
3. Start backend once:
```bash
python -m services.main
```
4. Verify users:
```bash
python -m services.admin_users list-users
```
5. Turn auto-seed back off:
```env
AUTH_AUTO_SEED_USERS=false
```

## Common mistakes
- Typo in command name (example: `ython` instead of `python`).
- Running from wrong folder (`D:/Ai-testrig` instead of repo root).
- Not activating virtual environment.

## Move Further (next phase)
After auth is verified, continue with these improvements:
1. Add refresh-token flow (short-lived access token + refresh token).
2. Add password policy + forced reset flow for first login.
3. Add role-based endpoint guards beyond header-level role context.
4. Add audit logs for login attempts and user management actions.
5. Add rate-limiting for `/auth/login`.
