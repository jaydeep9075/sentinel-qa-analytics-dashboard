import logging
import litellm
from . import config

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self, provider: str = None, model: str = None):
        self.provider = provider or config.LLM_PROVIDER
        self.model = model or config.LLM_MODEL

    def generate(self, prompt: str, temperature: float = 0.2, max_tokens: int = 2000) -> str:
        try:
            model_str = f"{self.provider}/{self.model}"
            kwargs = dict(
                model=model_str,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if config.OPENAI_API_BASE:
                kwargs["api_base"] = config.OPENAI_API_BASE
            response = litellm.completion(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            return None
