"""
app_settings.py — Runtime-editable configuration, persisted in the same
SQLite database as auth (config.AUTH_USER_STORE_URL).

LLM provider/model/key/base-url and SECRET_KEY live here. Everything else in
config.py (ports, mount paths, CORS, ...) is read once at process start and a
container is already running with those values by the time any UI could
change them - genuinely runtime-editable settings are the narrow exception,
not the rule. See WORKLOG.md item 5 for why this split exists.

Resolution order for every field is **database > env > built-in default**:

  * database is what the admin Settings tab writes, and always wins once set.
    This is deliberate: a Docker image is meant to ship with nothing
    preconfigured, and whatever an admin sets from the UI - including
    switching providers/models later, or rotating SECRET_KEY - has to stick
    even if .env still has an old value sitting in it from how the container
    was first brought up. Nothing here is "locked" by env anymore.
  * env is the seed for a fresh deployment that hasn't been configured from
    the UI yet (or is intentionally pinned via infra and never will be -
    nothing forces you to use the admin UI, env still works exactly as
    before if you just never touch Settings).
  * default is config.py's per-provider table (gemini/openai/anthropic/ollama
    default models) for LLM fields, or the auto-generated state/secret_key
    file for SECRET_KEY (config.SECRET_KEY already resolves that tier).

The one wrinkle database>env>default doesn't cover on its own: the env-
resolved API key was historically computed against whichever provider
LLM_PROVIDER named at startup. If the admin changes the *provider* through
this module, the key has to be re-resolved against the NEW effective
provider, not the old one - see config.resolve_api_key_for_provider().
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy import DateTime, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from . import config

logger = logging.getLogger(__name__)

_KEYS = ("llm_provider", "llm_model", "llm_api_key", "llm_api_base")


class Base(DeclarativeBase):
    pass


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)


_engine = create_engine(config.AUTH_USER_STORE_URL, future=True)
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
Base.metadata.create_all(_engine)


def _get_raw(key: str) -> Optional[str]:
    with _SessionLocal() as session:
        row = session.get(AppSetting, key)
        return row.value if row else None


def _set_raw(key: str, value: str, updated_by: str) -> None:
    with _SessionLocal() as session:
        row = session.get(AppSetting, key)
        if row is None:
            row = AppSetting(key=key)
            session.add(row)
        row.value = value
        row.updated_by = updated_by or None
        row.updated_at = datetime.now(timezone.utc)
        session.commit()


def mask_api_key(key: str) -> str:
    """Never return a usable credential over the API. Shows just enough to
    confirm which key is configured without letting a network capture (or a
    lower-privileged viewer of a screen-share) read it out."""
    key = str(key or "")
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}{'•' * 8}{key[-4:]}"


def get_llm_settings(include_secret: bool = False) -> Dict[str, object]:
    """The EFFECTIVE provider/model/key/base right now, per field, with which
    source won and whether the admin console may edit it.

    `include_secret=True` returns the real api_key (only for the code path
    that actually calls the LLM - llm_client.py); every API response instead
    uses the masked form from mask_api_key().
    """
    db_provider = _get_raw("llm_provider")
    db_model = _get_raw("llm_model")
    db_api_key = _get_raw("llm_api_key")
    db_api_base = _get_raw("llm_api_base")

    if db_provider:
        provider, provider_source = db_provider, "database"
    elif config.LLM_PROVIDER_FROM_ENV:
        provider, provider_source = config.LLM_PROVIDER, "env"
    else:
        provider, provider_source = config.LLM_PROVIDER, "default"

    if db_model:
        model, model_source = db_model, "database"
    elif config.LLM_MODEL_FROM_ENV:
        model, model_source = config.LLM_MODEL, "env"
    else:
        model, model_source = config.default_model_for(provider), "default"

    # Re-resolved against the EFFECTIVE provider, not the startup-time one -
    # see the module docstring.
    env_key_for_provider = config.resolve_api_key_for_provider(provider)
    if db_api_key:
        api_key, api_key_source = db_api_key, "database"
    elif env_key_for_provider:
        api_key, api_key_source = env_key_for_provider, "env"
    else:
        api_key, api_key_source = "", "default"

    if db_api_base:
        api_base, api_base_source = db_api_base, "database"
    elif config.LLM_API_BASE_FROM_ENV:
        api_base, api_base_source = config.LLM_API_BASE, "env"
    else:
        api_base, api_base_source = "", "default"

    result = {
        "provider": provider,
        # Nothing is env-locked anymore (database always wins once set) -
        # kept as a field for frontend compatibility, always False now.
        "provider_locked": False,
        "provider_source": provider_source,
        "model": model,
        "model_locked": False,
        "model_source": model_source,
        "api_key_set": bool(api_key),
        "api_key_locked": False,
        "api_key_source": api_key_source,
        "api_key_masked": mask_api_key(api_key),
        "api_base": api_base,
        "api_base_locked": False,
        "api_base_source": api_base_source,
        "keyless": config.provider_is_keyless(provider),
    }
    if include_secret:
        result["api_key"] = api_key
    return result


def update_llm_settings(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    clear_api_key: bool = False,
    updated_by: str = "",
) -> Dict[str, object]:
    """Persist an admin's edit. `None` means "leave this field alone" for
    provider/model/api_base; api_key additionally supports `clear_api_key`
    since "" can't distinguish "don't touch it" from "remove it" the way it
    can for the other fields (an admin legitimately wants to blank a stored
    key when switching to a keyless provider).

    Validates the RESULTING combination before writing anything, via the same
    config.validate_llm_config() the old startup check used - so a typo that
    would have failed at boot instead fails immediately, in this call, before
    it's saved.
    """
    if provider is not None:
        _set_raw("llm_provider", provider.strip().lower(), updated_by)
    if model is not None:
        _set_raw("llm_model", model.strip(), updated_by)
    if api_base is not None:
        _set_raw("llm_api_base", api_base.strip(), updated_by)
    if clear_api_key:
        _set_raw("llm_api_key", "", updated_by)
    elif api_key is not None and api_key.strip():
        _set_raw("llm_api_key", api_key.strip(), updated_by)

    updated = get_llm_settings(include_secret=True)
    config.validate_llm_config(
        provider=updated["provider"],
        model=updated["model"],
        api_key=updated["api_key"],
        api_base=updated["api_base"],
    )
    logger.info(
        "LLM settings updated by '%s': provider=%s model=%s api_key_set=%s api_base=%s",
        updated_by, updated["provider"], updated["model"],
        bool(updated["api_key"]), updated["api_base"] or "-",
    )
    return get_llm_settings(include_secret=False)


def test_llm_settings(
    provider: str,
    model: str,
    api_key: str = "",
    api_base: str = "",
    timeout_seconds: float = 15.0,
) -> Dict[str, object]:
    """Fire one minimal real completion against a CANDIDATE configuration,
    without persisting it. Backs the Settings tab's "Test connection" button -
    validate_llm_config() only catches shape errors (missing key, provider/
    model mismatch); this is the only way to catch a key that's well-formed
    but wrong, or a model name that doesn't exist for that account.
    """
    import litellm

    config.validate_llm_config(provider=provider, model=model, api_key=api_key, api_base=api_base)

    model_str = model if "/" in model else f"{provider}/{model}"
    kwargs = dict(
        model=model_str,
        messages=[{"role": "user", "content": "Reply with the single word: OK"}],
        max_tokens=5,
        temperature=0,
        timeout=timeout_seconds,
    )
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base
    elif provider == "ollama":
        kwargs["api_base"] = config.OLLAMA_URL

    try:
        response = litellm.completion(**kwargs)
        reply = (response.choices[0].message.content or "").strip()
        return {"success": True, "model": model_str, "reply": reply}
    except Exception as exc:
        return {"success": False, "model": model_str, "error": str(exc)}


# --- SECRET_KEY ---------------------------------------------------------
#
# Same database > env > default precedence as the LLM fields, but with two
# differences that matter enough to keep this separate rather than folding
# it into _KEYS/get_llm_settings:
#
#   1. auth.py calls get_secret_key() fresh on every token sign/verify (see
#      auth.SECRET_KEY / __getattr__ in that module) - never cached at
#      import time - so an admin's change takes effect on the very next
#      request, no restart needed.
#   2. Changing it invalidates every currently-issued JWT immediately: every
#      logged-in user (including whoever just changed it) is signed out on
#      their next request. That's inherent to what a signing secret is, not
#      a bug - callers must surface a clear warning before calling
#      set_secret_key(), not treat it like an ordinary settings save.

def get_secret_key() -> str:
    """The signing secret every JWT is created/verified against RIGHT NOW.
    Read fresh - do not cache the return value across requests."""
    db_value = _get_raw("secret_key")
    if db_value:
        return db_value
    return config.SECRET_KEY


def get_secret_key_info() -> Dict[str, object]:
    """Masked - never return the usable secret over the admin API."""
    db_value = _get_raw("secret_key")
    if db_value:
        source = "database"
    elif config.SECRET_KEY_FROM_ENV:
        source = "env"
    else:
        source = "auto-generated"
    return {
        "source": source,
        "masked": mask_api_key(db_value or config.SECRET_KEY),
    }


def set_secret_key(value: str, updated_by: str) -> None:
    value = (value or "").strip()
    if len(value) < 32:
        raise ValueError("SECRET_KEY must be at least 32 characters")
    _set_raw("secret_key", value, updated_by)
    logger.warning(
        "SECRET_KEY changed by '%s' - every existing session (including "
        "theirs) is now invalid and must log in again.",
        updated_by,
    )


def generate_secret_key(updated_by: str) -> str:
    """Let the admin UI offer "generate one for me" instead of requiring a
    human to paste 32+ random characters correctly."""
    import secrets as _secrets
    value = _secrets.token_urlsafe(48)
    set_secret_key(value, updated_by)
    return value


# --- Embedding model -----------------------------------------------------
#
# Same database > env > default precedence as the LLM fields. Kept separate
# from get_llm_settings()/_KEYS because it's an independent axis - the
# embedding model stays a local sentence-transformers model regardless of
# which hosted LLM_PROVIDER is chosen for chat/chart generation.

def get_embedding_model_settings() -> Dict[str, object]:
    db_value = _get_raw("embedding_model")
    if db_value:
        return {"model": db_value, "source": "database"}
    if config.EMBEDDING_MODEL_FROM_ENV:
        return {"model": config.EMBEDDING_MODEL, "source": "env"}
    return {"model": config.EMBEDDING_MODEL_DEFAULT, "source": "default"}


def get_effective_embedding_model() -> str:
    """Read fresh, not cached - the embedder singleton (services/data_loader.py)
    compares this against what it was last built with and rebuilds itself if
    an admin changes it from the Settings page, so a change here takes effect
    on the next vector-search call with no restart needed."""
    return str(get_embedding_model_settings()["model"])


def update_embedding_model(model: str, updated_by: str) -> Dict[str, object]:
    model = (model or "").strip()
    if not model:
        raise ValueError("Embedding model name is required")
    _set_raw("embedding_model", model, updated_by)
    logger.info("Embedding model updated by '%s': %s", updated_by, model)
    return get_embedding_model_settings()
