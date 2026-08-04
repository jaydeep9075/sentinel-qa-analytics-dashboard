import logging
import litellm
from . import config, state
from . import app_settings, token_usage_store

logger = logging.getLogger(__name__)


class LLMNotConfiguredError(Exception):
    """No usable provider/model/key combination is currently configured.

    Distinct from a plain generation failure (rate limit, network blip):
    this means there is nothing to even attempt, which the caller should
    surface as "ask an admin to finish setup" rather than "try again".
    """


class LLMClient:
    def __init__(self, provider: str = None, model: str = None):
        # An explicit constructor arg always wins (a few callers pin a
        # specific model). Otherwise resolved fresh from app_settings on
        # EVERY call below, not cached on self at construction time - an
        # admin changing the provider in the Settings tab must take effect
        # for the next request without a restart, and LLMClient() is
        # constructed per-request throughout handlers.py, not once at
        # startup, so there is no long-lived instance whose staleness would
        # matter.
        self._provider_override = provider
        self._model_override = model

    def _effective_settings(self) -> dict:
        settings = app_settings.get_llm_settings(include_secret=True)
        if self._provider_override:
            settings["provider"] = self._provider_override
        if self._model_override:
            settings["model"] = self._model_override
        return settings

    def _resolve_model_name(self, settings: dict) -> str:
        model = (settings.get("model") or "").strip()
        provider = (settings.get("provider") or "").strip()

        if not model:
            return provider
        # If model is already provider-qualified (or vendor/model), keep it.
        if "/" in model:
            return model
        if not provider:
            return model
        return f"{provider}/{model}"

    def _build_kwargs(self, prompt: str, temperature: float, max_tokens: int, settings: dict) -> dict:
        model_str = self._resolve_model_name(settings)
        kwargs = dict(
            model=model_str,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        api_key = settings.get("api_key") or ""
        api_base = settings.get("api_base") or ""
        if api_key:
            kwargs["api_key"] = api_key
        if api_base:
            kwargs["api_base"] = api_base
        elif (settings.get("provider") or "").strip().lower() == "ollama":
            kwargs["api_base"] = config.OLLAMA_URL
        return kwargs

    def _record_usage(self, response, model_str: str, user_id: str, workspace_id: str) -> None:
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", prompt_tokens + completion_tokens) or 0)

        state.token_usage["prompt_tokens"] += prompt_tokens
        state.token_usage["completion_tokens"] += completion_tokens
        state.token_usage["total_tokens"] += total_tokens
        state.token_usage["calls"] += 1

        model_key = model_str or "unknown"
        if model_key not in state.token_usage_by_model:
            state.token_usage_by_model[model_key] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "calls": 0,
            }
        state.token_usage_by_model[model_key]["prompt_tokens"] += prompt_tokens
        state.token_usage_by_model[model_key]["completion_tokens"] += completion_tokens
        state.token_usage_by_model[model_key]["total_tokens"] += total_tokens
        state.token_usage_by_model[model_key]["calls"] += 1

        token_usage_store.record_usage(
            user_id=user_id,
            workspace_id=workspace_id,
            model=model_key,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    def _check_configured(self, settings: dict) -> None:
        provider = (settings.get("provider") or "").strip()
        model = (settings.get("model") or "").strip()
        if not provider or not model:
            raise LLMNotConfiguredError(
                "No LLM provider/model configured. An administrator must set "
                "one in the Settings tab (or LLM_PROVIDER/LLM_MODEL in .env)."
            )
        if not settings.get("keyless") and not settings.get("api_key"):
            raise LLMNotConfiguredError(
                f"No API key configured for provider '{provider}'. An "
                f"administrator must set one in the Settings tab."
            )

    def generate(
        self,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        user_id: str = "anonymous",
        workspace_id: str = "default",
    ) -> str:
        try:
            settings = self._effective_settings()
            self._check_configured(settings)
            model_str = self._resolve_model_name(settings)
            kwargs = self._build_kwargs(prompt, temperature, max_tokens, settings)
            response = litellm.completion(**kwargs)
            self._record_usage(response, model_str, user_id, workspace_id)
            return response.choices[0].message.content
        except LLMNotConfiguredError as e:
            logger.warning(f"LLM not configured: {e}")
            return None
        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            return None

    async def agenerate(
        self,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        user_id: str = "anonymous",
        workspace_id: str = "default",
    ) -> str:
        """Async counterpart of generate(). Uses litellm's native async completion
        so a slow LLM call does not block the FastAPI event loop / other
        concurrent requests (dashboard load, other users' chats, etc.)."""
        try:
            settings = self._effective_settings()
            self._check_configured(settings)
            model_str = self._resolve_model_name(settings)
            kwargs = self._build_kwargs(prompt, temperature, max_tokens, settings)
            response = await litellm.acompletion(**kwargs)
            self._record_usage(response, model_str, user_id, workspace_id)
            return response.choices[0].message.content
        except LLMNotConfiguredError as e:
            logger.warning(f"LLM not configured: {e}")
            return None
        except Exception as e:
            logger.error(f"LLM async generation error: {e}")
            return None
