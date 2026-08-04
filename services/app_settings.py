"""
app_settings.py — Runtime-editable configuration, persisted in the same
SQLite database as auth (config.AUTH_USER_STORE_URL).

Only the LLM provider/model/key/base-url live here today. Everything else in
config.py (ports, mount paths, CORS, SECRET_KEY, ...) is read once at process
start and a container is already running with those values by the time any
UI could change them - genuinely runtime-editable settings are the narrow
exception, not the rule. See WORKLOG.md item 5 for why this split exists.

Resolution order for every field is **env > database > built-in default**:

  * env stays authoritative so a pinned production config (k8s secret, a
    provisioning script) can never be silently overridden by someone with
    admin-console access - the corresponding input is disabled in the UI and
    `locked` is reported alongside the value so the frontend knows to do that.
  * database is what the admin Settings tab writes. It is what makes the
    first-run setup path work without touching .env at all.
  * default is config.py's per-provider table (gemini/openai/anthropic/ollama
    default models), same as it always was.

The one wrinkle env>DB>default doesn't cover on its own: the env-resolved API
key was historically computed ONCE at import time, against whichever provider
LLM_PROVIDER named at startup. If the admin changes the *provider* through
this module (not through .env), the key has to be re-resolved against the
NEW effective provider, not the old one - see config.resolve_api_key_for_provider().
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

    if config.LLM_PROVIDER_FROM_ENV:
        provider, provider_source = config.LLM_PROVIDER, "env"
    elif db_provider:
        provider, provider_source = db_provider, "database"
    else:
        provider, provider_source = config.LLM_PROVIDER, "default"

    if config.LLM_MODEL_FROM_ENV:
        model, model_source = config.LLM_MODEL, "env"
    elif db_model:
        model, model_source = db_model, "database"
    else:
        model, model_source = config.default_model_for(provider), "default"

    # Re-resolved against the EFFECTIVE provider, not the startup-time one -
    # see the module docstring.
    env_key_for_provider = config.resolve_api_key_for_provider(provider)
    if env_key_for_provider:
        api_key, api_key_source = env_key_for_provider, "env"
    elif db_api_key:
        api_key, api_key_source = db_api_key, "database"
    else:
        api_key, api_key_source = "", "default"

    if config.LLM_API_BASE_FROM_ENV:
        api_base, api_base_source = config.LLM_API_BASE, "env"
    elif db_api_base:
        api_base, api_base_source = db_api_base, "database"
    else:
        api_base, api_base_source = "", "default"

    result = {
        "provider": provider,
        "provider_locked": provider_source == "env",
        "provider_source": provider_source,
        "model": model,
        "model_locked": model_source == "env",
        "model_source": model_source,
        "api_key_set": bool(api_key),
        "api_key_locked": api_key_source == "env",
        "api_key_source": api_key_source,
        "api_key_masked": mask_api_key(api_key),
        "api_base": api_base,
        "api_base_locked": api_base_source == "env",
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

    Validates the RESULTING combination (this edit merged with whatever env
    still locks) before writing anything, via the same
    config.validate_llm_config() the old startup check used - so a typo that
    would have failed at boot instead fails immediately, in this call, before
    it's saved.
    """
    current = get_llm_settings(include_secret=True)

    if provider is not None and not current["provider_locked"]:
        _set_raw("llm_provider", provider.strip().lower(), updated_by)
    if model is not None and not current["model_locked"]:
        _set_raw("llm_model", model.strip(), updated_by)
    if api_base is not None and not current["api_base_locked"]:
        _set_raw("llm_api_base", api_base.strip(), updated_by)
    if not current["api_key_locked"]:
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
