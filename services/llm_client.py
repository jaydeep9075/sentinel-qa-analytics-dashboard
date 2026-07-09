import logging
import litellm
from . import config

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

    def generate(self, prompt: str, temperature: float = 0.2, max_tokens: int = 2000) -> str:
        try:
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
            response = litellm.completion(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            return None
