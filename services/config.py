
import json
import logging
import os
import secrets
import stat
from pathlib import Path
from dotenv import load_dotenv

from universal_ingester.utils import DEFAULT_EMBEDDING_MODEL

load_dotenv()

logger = logging.getLogger(__name__)

# Base directory where all ingestion folders live.
#
# Env-driven rather than hardcoded to BASE_DIR/"data" so the SAME image can be
# pointed at a bind mount, a cloud block volume, or a mounted network share
# without rebuilding. The variable name matches the one the frontend's
# /api/builds route already reads, so a single value configures both services.
# Unset (a plain repo checkout) keeps the original behaviour.
BASE_DIR = Path(__file__).parent.parent
DATA_BASE_PATH = Path(os.getenv("SENTINEL_DATA_DIR") or (BASE_DIR / "data")).expanduser()
DATA_BASE_PATH.mkdir(parents=True, exist_ok=True)

# Mutable app state that is neither ingested data nor configuration: the auth
# database and the ingester's config2.json.
#
# These are kept in a DIRECTORY that compose bind-mounts, rather than being
# bind-mounted as individual files. Docker will pass a single file through
# only if it already exists on the host - otherwise it creates a directory
# with that name and the app fails confusingly. Mounting the parent directory
# means Docker creates whatever is missing and the files are seeded below, so
# a fresh clone needs no `touch users.db` step.
STATE_DIR = Path(os.getenv("SENTINEL_STATE_DIR") or (BASE_DIR / "state")).expanduser()
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Where the one-shot ingester and the dashboard's "Add Build" box read/write
# the ingestion config.
CONFIG2_PATH = Path(
    os.getenv("SENTINEL_CONFIG2_PATH") or (STATE_DIR / "config2.json")
).expanduser()


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_origins(raw: str) -> list[str]:
    if not raw:
        return ["http://localhost:3000"]
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["http://localhost:3000"]

# --- LLM -------------------------------------------------------------------
#
# Three things come from outside and nothing is hardcoded: WHICH provider,
# WHICH model, and WHICH key. Switching vendors is a .env edit + restart, with
# no code change and no rebuild (these are read at process start, and compose
# passes them through as plain runtime env).
#
# Any provider litellm supports works, not just the four in the table below.
# The table only supplies *conveniences* - a sensible default model and the
# conventional name of the key variable - so unknown providers are allowed
# through as long as you name the model explicitly. That's deliberate: litellm
# adds vendors faster than this file can be updated, and a whitelist here
# would reject a perfectly valid config for no reason.
# No built-in fallback provider on purpose: a public/open-source deployment
# should ship with nothing pre-selected, so a fresh install shows an empty
# Settings tab rather than a vendor the operator never chose. Set LLM_PROVIDER
# in .env, or pick one later from Admin -> Settings.
LLM_PROVIDER = (os.getenv("LLM_PROVIDER") or "").strip().lower()

# Which env var conventionally holds each provider's credential, in priority
# order. Providers not listed fall back to <PROVIDER>_API_KEY then LLM_API_KEY.
_PROVIDER_KEY_VARS = {
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "azure": ("AZURE_API_KEY",),
    "mistral": ("MISTRAL_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "cohere": ("COHERE_API_KEY",),
    "deepseek": ("DEEPSEEK_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
    "together_ai": ("TOGETHERAI_API_KEY",),
    "bedrock": (),   # credentials come from the AWS chain, not a single key
    "vertex_ai": (), # credentials come from GOOGLE_APPLICATION_CREDENTIALS
    "ollama": (),    # local, no credential
}

# Providers that legitimately run with no API key at all. Everything else has
# to produce one (or point LLM_API_BASE at a gateway that injects it).
KEYLESS_LLM_PROVIDERS = frozenset({"ollama", "bedrock", "vertex_ai"})

# litellm addresses every model as `provider/model`, so the prefix is part of
# the id - see llm_client._resolve_model_name().
_PROVIDER_DEFAULT_MODEL = {
    "gemini": "gemini/gemini-2.5-flash",
    "openai": "openai/gpt-4o-mini",
    "anthropic": "anthropic/claude-opus-5",
    "ollama": "ollama/llama3",
}

# "Known" == this file can guess a default model / key var for it. NOT a
# whitelist; see KNOWN_LLM_PROVIDERS usage in validate_runtime_config().
KNOWN_LLM_PROVIDERS = tuple(sorted(set(_PROVIDER_KEY_VARS) | set(_PROVIDER_DEFAULT_MODEL)))


def _provider_key_vars(provider: str) -> tuple:
    """Env var names to try for `provider`, most specific first.

    Known providers use their conventional name; anything else gets the
    <PROVIDER>_API_KEY convention litellm itself follows, so a vendor this
    file has never heard of still picks up its own key automatically.
    """
    if provider in _PROVIDER_KEY_VARS:
        return _PROVIDER_KEY_VARS[provider]
    slug = "".join(ch if ch.isalnum() else "_" for ch in provider).strip("_").upper()
    return (f"{slug}_API_KEY",) if slug else ()


def _resolve_llm_api_key(provider: str) -> str:
    """The active provider's own key wins over the generic LLM_API_KEY.

    The previous order was LLM_API_KEY first, then *any* provider key it could
    find - which meant flipping LLM_PROVIDER from gemini to anthropic kept
    sending the Gemini key to Anthropic. That fails as a 401 from the provider
    with nothing in the config looking wrong, which is a miserable thing to
    debug. Checking the provider-specific var first lets every key sit in .env
    simultaneously and makes switching providers genuinely one line.

    LLM_API_KEY stays as the fallback so the simplest possible setup - one
    provider, one key, no vendor-specific variable - keeps working.
    """
    for name in _provider_key_vars(provider):
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return (os.getenv("LLM_API_KEY") or "").strip()


LLM_API_KEY = _resolve_llm_api_key(LLM_PROVIDER)
LLM_MODEL = (os.getenv("LLM_MODEL") or _PROVIDER_DEFAULT_MODEL.get(LLM_PROVIDER, "")).strip()

# Which of the three came from the environment, as opposed to being a default
# this file invented. app_settings.py needs the distinction to implement
# `env > database > default`: an admin editing the LLM settings in the UI must
# be able to override a *default*, but must NOT be able to override a value the
# operator pinned in .env - otherwise a deployment's pinned provider could be
# changed from a browser, and the change would silently revert on restart.
LLM_PROVIDER_FROM_ENV = bool((os.getenv("LLM_PROVIDER") or "").strip())
LLM_MODEL_FROM_ENV = bool((os.getenv("LLM_MODEL") or "").strip())
LLM_API_KEY_FROM_ENV = bool(LLM_API_KEY)
LLM_API_BASE_FROM_ENV = bool((os.getenv("LLM_API_BASE") or os.getenv("OPENAI_API_BASE") or "").strip())

# Local sentence-transformers model used to embed ingested documents for
# semantic/vector search - independent of LLM_PROVIDER/LLM_MODEL above (those
# are the hosted chat/generation model; embeddings stay local so ingesting
# thousands of chunks doesn't cost API calls). Same database > env > default
# resolution as the LLM settings - see app_settings.get_embedding_model_settings().
# Default comes from universal_ingester.utils - the single source of truth
# for the model name, so this and EmbeddingGenerator's own default can't
# silently drift apart.
EMBEDDING_MODEL_DEFAULT = DEFAULT_EMBEDDING_MODEL
EMBEDDING_MODEL = (os.getenv("EMBEDDING_MODEL") or EMBEDDING_MODEL_DEFAULT).strip()
EMBEDDING_MODEL_FROM_ENV = bool((os.getenv("EMBEDDING_MODEL") or "").strip())


def default_model_for(provider: str) -> str:
    return _PROVIDER_DEFAULT_MODEL.get((provider or "").strip().lower(), "")


def resolve_api_key_for_provider(provider: str) -> str:
    """Public wrapper: app_settings.py needs this to re-check the env for
    whichever provider is EFFECTIVE at read time (env, then DB, then
    default) - not necessarily the provider LLM_PROVIDER named at process
    start. See app_settings.get_llm_settings()."""
    return _resolve_llm_api_key(provider)


def provider_is_keyless(provider: str) -> bool:
    return (provider or "").strip().lower() in KEYLESS_LLM_PROVIDERS


def validate_llm_config(
    provider: str,
    model: str,
    api_key: str = "",
    api_base: str = "",
) -> None:
    """Raise ValueError if this combination cannot possibly work.

    Split out of validate_runtime_config() so the same rules apply to a
    configuration typed into the admin Settings tab as to one read from .env -
    there is exactly one definition of "valid", and the UI can reject a bad
    edit before saving it rather than leaving the operator to discover the
    problem on the next restart.
    """
    provider = (provider or "").strip().lower()
    model = (model or "").strip()

    if not provider:
        raise ValueError("LLM provider is required")

    if provider not in KNOWN_LLM_PROVIDERS and not model:
        # Not an error in itself. litellm supports far more vendors than this
        # file enumerates, so an unrecognised provider is allowed through -
        # but the model id is the one thing that cannot be guessed for it.
        raise ValueError(
            f"Provider '{provider}' is not one this build knows a default model "
            f"for, so the model must be set explicitly (e.g. {provider}/<model-name>). "
            f"Providers with built-in defaults: {', '.join(sorted(_PROVIDER_DEFAULT_MODEL))}."
        )

    if not model:
        raise ValueError("LLM model is required")

    # Catch the mismatch that would otherwise surface as a confusing failure
    # from the wrong vendor's API: the provider says one thing, the model's
    # litellm prefix says another (e.g. provider=anthropic with
    # model=gemini/gemini-2.5-flash left over from a previous setup).
    # Only checked when BOTH sides name a provider this file recognises -
    # otherwise a legitimate `openai/org-name/model` style id would trip it.
    if "/" in model:
        model_prefix = model.split("/", 1)[0].strip().lower()
        if (
            model_prefix != provider
            and model_prefix in KNOWN_LLM_PROVIDERS
            and provider in KNOWN_LLM_PROVIDERS
        ):
            suggestion = _PROVIDER_DEFAULT_MODEL.get(provider, f"{provider}/<model-name>")
            raise ValueError(
                f"Provider is '{provider}' but the model '{model}' targets "
                f"'{model_prefix}'. Use a {provider} model (e.g. '{suggestion}'), "
                f"or change the provider to '{model_prefix}'."
            )

    # A gateway (LiteLLM proxy, vLLM, an enterprise egress proxy) normally
    # holds the real vendor credential itself, so an api_base being set is a
    # legitimate reason to have no key here.
    if provider not in KEYLESS_LLM_PROVIDERS and not api_key and not api_base:
        expected = _provider_key_vars(provider)
        hint = f"{expected[0]} (or LLM_API_KEY)" if expected else "LLM_API_KEY"
        raise ValueError(
            f"No API key configured for provider '{provider}'. Set {hint} in "
            f".env or in the admin Settings tab, or set an API base URL if a "
            f"gateway supplies the credential, or switch to provider 'ollama' "
            f"for local inference."
        )
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
# Point at an OpenAI-compatible gateway (LiteLLM proxy, vLLM, LocalAI, an
# enterprise egress proxy...). Setting this also satisfies the API-key check:
# gateways commonly hold the real credential themselves.
LLM_API_BASE = os.getenv("LLM_API_BASE") or os.getenv("OPENAI_API_BASE") or ""

# --- Security ---------------------------------------------------------------
#
# SECRET_KEY signs every JWT, so it has to exist before anyone can log in -
# which makes it the one value a first-run setup screen cannot ask for. When
# it isn't supplied we generate one into the mounted state directory instead
# of asking, so `docker compose up` with an empty .env produces a working,
# properly-signed deployment rather than a startup failure.
#
# Env still wins when set, which is what keeps cloud/K8s deploys (where the
# secret comes from a secret manager and the filesystem may be read-only or
# per-replica ephemeral) behaving exactly as before. The generated file is
# the fallback for the single-host case, and it MUST persist: regenerating it
# invalidates every issued token, silently logging everyone out on restart.
SECRET_KEY_FILE = STATE_DIR / "secret_key"


def _resolve_secret_key() -> str:
    env_value = (os.getenv("SECRET_KEY") or "").strip()
    if env_value:
        return env_value

    try:
        if SECRET_KEY_FILE.exists():
            stored = SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
            if len(stored) >= 32:
                return stored
            logger.warning(
                "%s holds a key shorter than 32 characters - regenerating it. "
                "Existing sessions will be signed out.", SECRET_KEY_FILE,
            )

        generated = secrets.token_urlsafe(48)
        SECRET_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        SECRET_KEY_FILE.write_text(generated + "\n", encoding="utf-8")
        try:
            # Owner-only. Best-effort: no-op semantics on Windows, and a
            # restrictive umask or a mounted volume may refuse it outright.
            SECRET_KEY_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        logger.warning(
            "SECRET_KEY was not set - generated one at %s. Keep this file with "
            "your backups: deleting it signs every user out.", SECRET_KEY_FILE,
        )
        return generated
    except Exception:
        # An unwritable state directory shouldn't take the whole service down
        # when the operator can still supply SECRET_KEY themselves - but the
        # process must not silently run on a key that dies with it, so this
        # falls through to validate_runtime_config()'s hard failure.
        logger.error("Could not read or create %s", SECRET_KEY_FILE, exc_info=True)
        return ""


SECRET_KEY = _resolve_secret_key()
# Whether env supplied it (vs the auto-generated state/secret_key file) -
# app_settings.py uses this to label the source in the admin Settings UI.
# Doesn't change precedence: an admin-set value in the database always wins
# over either of these now (see app_settings.get_secret_key()).
SECRET_KEY_FROM_ENV = bool((os.getenv("SECRET_KEY") or "").strip())
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))

# CORS
CORS_ALLOWED_ORIGINS = _parse_origins(os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000"))

# Auth storage (free, local defaults)
AUTH_BACKEND = os.getenv("AUTH_BACKEND", "db").strip().lower()  # db | memory
AUTH_USER_STORE_URL = os.getenv(
    "AUTH_USER_STORE_URL", f"sqlite:///{(STATE_DIR / 'users.db').as_posix()}"
)
AUTH_AUTO_SEED_USERS = _get_bool("AUTH_AUTO_SEED_USERS", False)
AUTH_SEED_FILE = os.getenv("AUTH_SEED_FILE", str(BASE_DIR / "auth_seed_users.json"))

# --- Registration ----------------------------------------------------------
# Self-service signup. On by default so a fresh deployment is usable without
# shell access, but new accounts land in `pending` and CANNOT log in until an
# admin approves them and assigns a workspace. That ordering is the whole
# point: it lets people request access through the UI while keeping the two
# things that decide what they can see - role and workspace - under admin
# control rather than under the control of whoever filled in the form.
AUTH_ALLOW_SELF_REGISTRATION = _get_bool("AUTH_ALLOW_SELF_REGISTRATION", True)
# Skip the approval queue entirely: registrations become active immediately in
# AUTH_DEFAULT_WORKSPACE with AUTH_DEFAULT_ROLE. Only sane for a trusted
# network (an internal demo, a single-team install) - it means anyone who can
# reach the login page can read that workspace's builds.
AUTH_AUTO_APPROVE_REGISTRATION = _get_bool("AUTH_AUTO_APPROVE_REGISTRATION", False)
# Role and workspace given to an approved registration when the admin doesn't
# specify. `viewer` is the least-privileged role the dashboard understands.
AUTH_DEFAULT_ROLE = (os.getenv("AUTH_DEFAULT_ROLE") or "viewer").strip().lower() or "viewer"

# --- First-run bootstrap admin ---------------------------------------------
# Creates one admin ONLY when the users table is completely empty, so a fresh
# container is reachable with nothing configured at all. It is not an
# override: once any user exists this is ignored, and changing the password
# here later does nothing.
#
# Both username and password default to a known "admin"/"admin" pair, so
# `docker compose up` on an empty .env always yields a deployment you can
# actually sign into - the appliance pattern (a router, Grafana, Jenkins).
# That's only safe because the account this creates cannot do anything else:
# must_change_password is forced on whenever the password in use is still
# this literal built-in default (see bootstrap_password_is_default() and
# auth._bootstrap_admin_if_empty()), regardless of
# BOOTSTRAP_ADMIN_FORCE_PASSWORD_CHANGE - so it's a one-time door, not a
# standing credential, the same way the old auto-generated-password design
# was, just guessable instead of unguessable. Set BOOTSTRAP_ADMIN_PASSWORD in
# .env instead if you want the first-run credential to not even briefly be
# something guessable.
DEFAULT_BOOTSTRAP_ADMIN_USERNAME = "admin"
DEFAULT_BOOTSTRAP_ADMIN_PASSWORD = "admin"


def _resolve_bootstrap_admin_password() -> tuple[str, bool]:
    """Returns (password, is_default)."""
    env_value = (os.getenv("BOOTSTRAP_ADMIN_PASSWORD") or "").strip()
    if env_value:
        return env_value, False
    return DEFAULT_BOOTSTRAP_ADMIN_PASSWORD, True


BOOTSTRAP_ADMIN_USERNAME = (
    os.getenv("BOOTSTRAP_ADMIN_USERNAME") or DEFAULT_BOOTSTRAP_ADMIN_USERNAME
).strip().lower()
BOOTSTRAP_ADMIN_PASSWORD, _BOOTSTRAP_ADMIN_PASSWORD_WAS_GENERATED = _resolve_bootstrap_admin_password()
# Whether the bootstrapped admin must replace its credentials before the
# session is good for anything else. Default on even when an explicit
# password was supplied: that password sits in a plaintext .env forever, and
# rotating it through the UI is what gets it out of there. Set to false only
# where the password is injected from a secret manager per-boot.
BOOTSTRAP_ADMIN_FORCE_PASSWORD_CHANGE = _get_bool(
    "BOOTSTRAP_ADMIN_FORCE_PASSWORD_CHANGE", True
)


def bootstrap_password_is_default() -> bool:
    """True when BOOTSTRAP_ADMIN_PASSWORD is the literal built-in default
    ("admin") rather than set explicitly via env - gates "is this the
    unattended first-run credential, not something an operator chose"
    (auth._bootstrap_admin_if_empty() forces a password change either way,
    but treats this case as always-force regardless of
    BOOTSTRAP_ADMIN_FORCE_PASSWORD_CHANGE).
    """
    return _BOOTSTRAP_ADMIN_PASSWORD_WAS_GENERATED


# Minimum length for any password a human sets through the UI or the CLI.
# The built-in default deliberately doesn't meet it - it is not a password
# anyone is allowed to keep, it's a one-time door.
MIN_PASSWORD_LENGTH = int(os.getenv("MIN_PASSWORD_LENGTH", "8"))

# Misc
MAX_HISTORY_TURNS = 10
DEFAULT_WORKSPACE_ID = os.getenv("DEFAULT_WORKSPACE_ID", "default").strip().lower() or "default"
AUTH_DEFAULT_WORKSPACE = (
    os.getenv("AUTH_DEFAULT_WORKSPACE") or DEFAULT_WORKSPACE_ID
).strip().lower() or DEFAULT_WORKSPACE_ID

# --- Build visibility ------------------------------------------------------
# Every build ingested from here on records an owner.json naming the workspace
# it belongs to, and non-admins only see builds from their own workspace.
# Builds that predate that file have no recorded owner; this says which
# workspace they count as. Defaults to the default workspace so an existing
# install doesn't suddenly hide its own history. Set to an unused value (e.g.
# "archive") to hide legacy builds from everyone except admins.
LEGACY_BUILDS_WORKSPACE = (
    os.getenv("LEGACY_BUILDS_WORKSPACE") or DEFAULT_WORKSPACE_ID
).strip().lower() or DEFAULT_WORKSPACE_ID

# Live test execution (reporter -> backend ingestion)
# Shared secret the @sentinel/playwright reporter sends as `x-api-key` to
# every /live/* ingestion route (services/live_exec/router.py's
# require_ingest_key). This used to default to "" (empty), which
# require_ingest_key treated as "endpoint unauthenticated" - convenient for
# a bare `playwright test` against localhost, but it means the DEFAULT
# state of a container reachable from any network beyond localhost is an
# open write endpoint anyone can post fake runs to. Same fix as SECRET_KEY
# and BOOTSTRAP_ADMIN_PASSWORD above: generate one into the mounted state
# directory when it isn't supplied, so the endpoint is authenticated by
# default instead of open by default, and log it once so it's actually
# usable - unlike SECRET_KEY, a human needs this value to configure
# SENTINEL_API_KEY in every Playwright repo that reports to this backend.
LIVE_INGEST_API_KEY_FILE = STATE_DIR / "live_ingest_api_key"


def _resolve_live_ingest_api_key() -> tuple[str, bool]:
    """Returns (key, was_generated)."""
    env_value = (os.getenv("LIVE_INGEST_API_KEY") or "").strip()
    if env_value:
        return env_value, False

    try:
        if LIVE_INGEST_API_KEY_FILE.exists():
            stored = LIVE_INGEST_API_KEY_FILE.read_text(encoding="utf-8").strip()
            if stored:
                return stored, True

        generated = secrets.token_urlsafe(32)
        LIVE_INGEST_API_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        LIVE_INGEST_API_KEY_FILE.write_text(generated + "\n", encoding="utf-8")
        try:
            LIVE_INGEST_API_KEY_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        return generated, True
    except Exception:
        # Unwritable state dir: fall through to "" rather than crash the
        # backend over a feature most deployments don't use.
        # require_ingest_key() treats "" as "unauthenticated, warn once" -
        # a safe degrade, not a silent one.
        logger.error("Could not read or create %s", LIVE_INGEST_API_KEY_FILE, exc_info=True)
        return "", False


LIVE_INGEST_API_KEY, _LIVE_INGEST_API_KEY_WAS_GENERATED = _resolve_live_ingest_api_key()
if LIVE_INGEST_API_KEY and _LIVE_INGEST_API_KEY_WAS_GENERATED:
    logger.warning(
        "LIVE_INGEST_API_KEY was not set - generated one at %s: '%s'. Use this "
        "as SENTINEL_API_KEY in any Playwright repo that reports live runs to "
        "this backend. Set LIVE_INGEST_API_KEY in .env instead if you'd rather "
        "choose it yourself (e.g. to share one value across multiple backend "
        "replicas that don't share a state directory).",
        LIVE_INGEST_API_KEY_FILE, LIVE_INGEST_API_KEY,
    )
LIVE_RUNS_DIR = DATA_BASE_PATH / "runs"
# Optional. Unset (default) = single-instance mode: the live SSE bus and
# live-frame cache stay in-process, which is correct and free as long as
# there's exactly one backend process. Set this only once you actually run
# more than one backend instance behind a load balancer - it makes the SSE
# push and live-frame cache work correctly across instances instead of only
# within whichever one instance happened to receive a given request. See
# services/live_exec/bus.py and screencast.py.
REDIS_URL = os.getenv("REDIS_URL", "")

# RBA: Projects and roles root directories
PROJECTS_ROOT = os.getenv("PROJECTS_ROOT", str(BASE_DIR / "projects"))
ROLES_ROOT = os.getenv("ROLES_ROOT", str(BASE_DIR / "roles"))

# Ingestion guards (background ingestion runs off the request thread, but
# still needs sane bounds so one huge/malformed source can't hang forever)
INGEST_MAX_FILE_SIZE_BYTES = int(os.getenv("INGEST_MAX_FILE_SIZE_BYTES", str(200 * 1024 * 1024)))
INGEST_MAX_ROWS = int(os.getenv("INGEST_MAX_ROWS", "500000"))
INGEST_TIMEOUT_SECONDS = float(os.getenv("INGEST_TIMEOUT_SECONDS", "600"))

# Number of ingestions kept "warm" (loaded LanceDB/DuckDB connections) at once.
# Switching between more than this many distinct ingestions evicts the least
# recently used one instead of paying a full reload every time it's revisited.
INGESTION_POOL_SIZE = int(os.getenv("INGESTION_POOL_SIZE", "3"))

# --- Auto-ingest watcher (services/auto_ingest.py) ---
# Off by default: enabling it means anything written into AUTO_INGEST_DIR gets
# ingested with no human in the loop, which is the right behaviour for a
# CI drop-box and the wrong one for a folder someone might use as scratch
# space. Opt in explicitly.
AUTO_INGEST_ENABLED = _get_bool("AUTO_INGEST_ENABLED", False)
# The watched drop-box. Defaults to the same ingest-source/ directory the
# compose file already mounts into the backend.
AUTO_INGEST_DIR = Path(
    os.getenv("AUTO_INGEST_DIR") or (BASE_DIR / "ingest-source")
).expanduser()
# How often to rescan. Each scan stats every top-level entry, so on a
# directory-shaped source this walks the tree - don't set it to 1s over a
# network mount holding thousands of files.
AUTO_INGEST_INTERVAL_SECONDS = float(os.getenv("AUTO_INGEST_INTERVAL_SECONDS", "30"))
# A new entry must keep the same size+mtime for this long before it's
# considered complete. This is what stops a half-uploaded 500MB zip from
# being handed to the ingester mid-write. Must be >= one scan interval to
# mean anything, so it's clamped to that below.
AUTO_INGEST_STABLE_SECONDS = float(os.getenv("AUTO_INGEST_STABLE_SECONDS", "20"))
# Which workspace a dropped file belongs to.
#
# The drop-box is a filesystem, so it has no caller to authenticate - the
# path IS the routing information. A file one level down, in
#   <AUTO_INGEST_DIR>/<workspace>/report.zip
# is ingested into that workspace; a file sitting at the top level goes to
# AUTO_INGEST_DEFAULT_WORKSPACE. That means "point a cloud bucket mount at
# this directory" works for a multi-team install without any per-team
# configuration: each team writes under its own prefix. Anyone who can write
# to the mount can write to any prefix, which is the correct threat model for
# a shared volume - use POST /ingest/upload with a scoped key when the
# producer shouldn't be trusted that far.
AUTO_INGEST_DEFAULT_WORKSPACE = (
    os.getenv("AUTO_INGEST_DEFAULT_WORKSPACE") or DEFAULT_WORKSPACE_ID
).strip().lower() or DEFAULT_WORKSPACE_ID

# --- Machine ingestion credentials -----------------------------------------
# CI jobs can't log in interactively, so POST /ingest/upload also accepts an
# `x-api-key`. Format: comma-separated key:workspace pairs, e.g.
#   INGEST_API_KEYS=ci-abc123:platform,ci-def456:mobile
# The key determines the workspace, so a leaked pipeline token can only write
# into the team it was issued for. Unset = JWT-only uploads.
def _parse_ingest_api_keys(raw: str) -> dict:
    mapping: dict[str, str] = {}
    for pair in (raw or "").split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        key, _, workspace = pair.partition(":")
        key = key.strip()
        workspace = workspace.strip().lower()
        if key and workspace:
            mapping[key] = workspace
    return mapping


INGEST_API_KEYS = _parse_ingest_api_keys(os.getenv("INGEST_API_KEYS", ""))
# Hard cap on a single uploaded artifact, checked while streaming to disk so a
# huge body is rejected rather than buffered. Separate from
# INGEST_MAX_FILE_SIZE_BYTES, which guards the ingester itself.
INGEST_UPLOAD_MAX_BYTES = int(
    os.getenv("INGEST_UPLOAD_MAX_BYTES", str(500 * 1024 * 1024))
)

# Cross-build chat/chart questions ("how are we trending", "compare to the
# last build"). Two different costs, two different caps:
# - Trend/comparison answers read only each build's small pre-aggregated
#   summary.json (a few KB each) - cheap regardless of history size, so this
#   just bounds how far back "recent builds" means, not a performance guard.
MAX_TREND_BUILDS = int(os.getenv("MAX_TREND_BUILDS", "12"))
# - Row-level cross-build SQL (e.g. "which tests failed in the last 3
#   builds") re-runs a real query against each build's full dataset - this
#   one IS a real latency guard, so it's deliberately small and independent
#   of how much ingestion history actually exists.
MAX_CROSS_BUILD_QUERY_BUILDS = int(os.getenv("MAX_CROSS_BUILD_QUERY_BUILDS", "5"))


def ensure_state_files() -> None:
    """Create anything a fresh deployment needs but can't be shipped in the image.

    config2.json is written to (the dashboard's "Add Build" box persists the
    path you type back into it), so it can't live in the read-only image - it
    has to exist in the mounted state directory. Seeding a valid default here
    means a brand-new container starts with a working file instead of the
    frontend 404-ing on /api/config2-path.

    Only ever creates. An existing file is never overwritten, so a user's
    edited config survives every restart and upgrade.
    """
    if CONFIG2_PATH.exists():
        return

    default_cfg = {
        "ingestion_name": "my_build",
        "sources": [
            {
                "type": "allure",
                "path": str(AUTO_INGEST_DIR / "allure-results.zip"),
            }
        ],
        "output": {"base_path": str(DATA_BASE_PATH)},
    }
    try:
        CONFIG2_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG2_PATH.write_text(
            json.dumps(default_cfg, indent=4, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        logger.info("Seeded default ingestion config at %s", CONFIG2_PATH)
    except Exception:
        # Not fatal: only the one-shot ingester and the "Add Build" path box
        # need this file, and both report their own errors clearly. Refusing
        # to start the whole backend over it would be a worse trade.
        logger.warning("Could not seed %s", CONFIG2_PATH, exc_info=True)


def validate_runtime_config() -> None:
    """Startup invariants that must hold before the app serves anything.

    The LLM configuration is deliberately NOT checked here any more. It used
    to be a hard startup failure, which was right when .env was the only way
    to supply it - but an administrator can now set the provider, model and
    key from the Settings tab, and refusing to start over a missing key would
    make that screen unreachable exactly when it's needed. A bad or absent LLM
    config is now a loud warning at boot (see main.lifespan) and a clear error
    at call time; everything that doesn't need an LLM keeps working meanwhile.
    """
    if not SECRET_KEY or len(SECRET_KEY) < 32:
        raise ValueError("SECRET_KEY must be set and at least 32 characters")

    if BCRYPT_ROUNDS < 10 or BCRYPT_ROUNDS > 16:
        raise ValueError("BCRYPT_ROUNDS must be between 10 and 16")

    if AUTH_BACKEND not in {"db", "memory"}:
        raise ValueError("AUTH_BACKEND must be either 'db' or 'memory'")

    Path(PROJECTS_ROOT).mkdir(parents=True, exist_ok=True)
    Path(ROLES_ROOT).mkdir(parents=True, exist_ok=True)