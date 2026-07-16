import logging
import litellm
from . import config, state
from . import token_usage_store

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self, provider: str = None, model: str = None):
        self.provider = provider or config.LLM_PROVIDER
        self.model = model or config.LLM_MODEL

    def _resolve_model_name(self) -> str:
        model = (self.model or "").strip()
        provider = (self.provider or "").strip()

        if not model:
            return provider

        # If model is already provider-qualified (or vendor/model), keep it.
        if "/" in model:
            return model

        if not provider:
            return model

        return f"{provider}/{model}"

    def _build_kwargs(self, prompt: str, temperature: float, max_tokens: int) -> dict:
        model_str = self._resolve_model_name()
        kwargs = dict(
            model=model_str,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if config.LLM_API_KEY:
            kwargs["api_key"] = config.LLM_API_KEY
        if config.LLM_API_BASE:
            kwargs["api_base"] = config.LLM_API_BASE
        elif (self.provider or "").strip().lower() == "ollama":
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

    def generate(
        self,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        user_id: str = "anonymous",
        workspace_id: str = "default",
    ) -> str:
        try:
            model_str = self._resolve_model_name()
            kwargs = self._build_kwargs(prompt, temperature, max_tokens)
            response = litellm.completion(**kwargs)
            self._record_usage(response, model_str, user_id, workspace_id)
            return response.choices[0].message.content
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
            model_str = self._resolve_model_name()
            kwargs = self._build_kwargs(prompt, temperature, max_tokens)
            response = await litellm.acompletion(**kwargs)
            self._record_usage(response, model_str, user_id, workspace_id)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM async generation error: {e}")
            return None
