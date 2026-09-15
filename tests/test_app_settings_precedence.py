"""LLM settings precedence: .env and the Settings tab are two authors, and
the one that changed a field most recently wins.

The old rule was "database always wins once set", which made editing .env a
permanent no-op after an admin's first save. These tests pin the handover in
both directions, per field.
"""

import importlib
import sys

import pytest


@pytest.fixture()
def settings(tmp_path, monkeypatch):
    """services.app_settings on a throwaway database and a controlled env.

    config.py reads the environment at import, so the module tree is purged
    and re-imported whenever a test wants .env to "have been edited".
    """
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    store_url = f"sqlite:///{(state_dir / 'users.db').as_posix()}"

    def reload_with(**env):
        monkeypatch.setenv("STATE_DIR", str(state_dir))
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("AUTH_USER_STORE_URL", store_url)
        monkeypatch.setenv("SECRET_KEY", "x" * 40)
        monkeypatch.setenv("AUTO_INGEST_ENABLED", "false")
        for name in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_API_BASE",
                     "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY",
                     "ANTHROPIC_API_KEY"):
            monkeypatch.delenv(name, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        for name in [m for m in sys.modules if m == "services" or m.startswith("services.")]:
            del sys.modules[name]
        return importlib.import_module("services.app_settings")

    return reload_with


def test_env_seeds_a_deployment_nobody_has_configured_yet(settings):
    app_settings = settings(LLM_PROVIDER="gemini", LLM_MODEL="gemini/gemini-2.5-flash",
                            LLM_API_KEY="env-key")
    current = app_settings.get_llm_settings(include_secret=True)
    assert (current["provider"], current["provider_source"]) == ("gemini", "env")
    assert (current["model"], current["model_source"]) == ("gemini/gemini-2.5-flash", "env")
    assert (current["api_key"], current["api_key_source"]) == ("env-key", "env")


def test_an_admin_save_overrides_env(settings):
    app_settings = settings(LLM_PROVIDER="gemini", LLM_MODEL="gemini/gemini-2.5-flash",
                            LLM_API_KEY="env-key")
    app_settings.update_llm_settings(model="gemini/gemini-2.5-pro", updated_by="admin")
    current = app_settings.get_llm_settings(include_secret=True)
    assert (current["model"], current["model_source"]) == ("gemini/gemini-2.5-pro", "database")
    # Untouched fields still come from env.
    assert current["provider_source"] == "env"


def test_an_admin_save_survives_a_restart(settings):
    app_settings = settings(LLM_PROVIDER="gemini", LLM_MODEL="gemini/gemini-2.5-flash",
                            LLM_API_KEY="env-key")
    app_settings.update_llm_settings(model="gemini/gemini-2.5-pro", updated_by="admin")

    # Same .env, fresh process: the admin is still the most recent author.
    app_settings = settings(LLM_PROVIDER="gemini", LLM_MODEL="gemini/gemini-2.5-flash",
                            LLM_API_KEY="env-key")
    current = app_settings.get_llm_settings()
    assert (current["model"], current["model_source"]) == ("gemini/gemini-2.5-pro", "database")


def test_editing_env_takes_back_over_from_a_saved_value(settings):
    # The whole point: this used to be ignored forever.
    app_settings = settings(LLM_PROVIDER="gemini", LLM_MODEL="gemini/gemini-2.5-flash",
                            LLM_API_KEY="env-key")
    app_settings.update_llm_settings(model="gemini/gemini-2.5-pro", updated_by="admin")

    app_settings = settings(LLM_PROVIDER="gemini", LLM_MODEL="gemini/gemini-3-flash",
                            LLM_API_KEY="env-key")
    current = app_settings.get_llm_settings()
    assert (current["model"], current["model_source"]) == ("gemini/gemini-3-flash", "env")


def test_a_rotated_key_in_env_beats_the_stored_one(settings):
    app_settings = settings(LLM_PROVIDER="gemini", LLM_MODEL="gemini/gemini-2.5-flash",
                            LLM_API_KEY="old-env-key")
    app_settings.update_llm_settings(api_key="key-from-ui", updated_by="admin")
    assert app_settings.get_llm_settings(include_secret=True)["api_key"] == "key-from-ui"

    app_settings = settings(LLM_PROVIDER="gemini", LLM_MODEL="gemini/gemini-2.5-flash",
                            LLM_API_KEY="rotated-env-key")
    current = app_settings.get_llm_settings(include_secret=True)
    assert (current["api_key"], current["api_key_source"]) == ("rotated-env-key", "env")


def test_switching_provider_in_env_repoints_the_key(settings):
    app_settings = settings(LLM_PROVIDER="gemini", LLM_MODEL="gemini/gemini-2.5-flash",
                            GEMINI_API_KEY="gemini-key", ANTHROPIC_API_KEY="anthropic-key")
    assert app_settings.get_llm_settings(include_secret=True)["api_key"] == "gemini-key"

    app_settings = settings(LLM_PROVIDER="anthropic", LLM_MODEL="anthropic/claude-opus-5",
                            GEMINI_API_KEY="gemini-key", ANTHROPIC_API_KEY="anthropic-key")
    current = app_settings.get_llm_settings(include_secret=True)
    assert (current["provider"], current["api_key"]) == ("anthropic", "anthropic-key")


def test_one_field_changing_in_env_leaves_other_saved_fields_alone(settings):
    app_settings = settings(LLM_PROVIDER="gemini", LLM_MODEL="gemini/gemini-2.5-flash",
                            LLM_API_KEY="env-key")
    app_settings.update_llm_settings(
        model="gemini/gemini-2.5-pro", api_key="key-from-ui", updated_by="admin"
    )

    # Only the model line changed in .env.
    app_settings = settings(LLM_PROVIDER="gemini", LLM_MODEL="gemini/gemini-3-flash",
                            LLM_API_KEY="env-key")
    current = app_settings.get_llm_settings(include_secret=True)
    assert (current["model"], current["model_source"]) == ("gemini/gemini-3-flash", "env")
    assert (current["api_key"], current["api_key_source"]) == ("key-from-ui", "database")


def test_a_saved_value_still_wins_when_env_says_nothing(settings):
    app_settings = settings()
    app_settings.update_llm_settings(
        provider="gemini", model="gemini/gemini-2.5-flash", api_key="key-from-ui",
        updated_by="admin",
    )
    app_settings = settings()
    current = app_settings.get_llm_settings(include_secret=True)
    assert (current["provider"], current["provider_source"]) == ("gemini", "database")
    assert (current["api_key"], current["api_key_source"]) == ("key-from-ui", "database")
