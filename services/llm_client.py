import logging
import requests
from . import config

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self, provider: str = None, api_key: str = None, model: str = None):
        self.provider = provider or config.LLM_PROVIDER
        self.model = model or config.LLM_MODEL
        self.api_key = api_key or config.LLM_API_KEY

        if self.provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.client = genai.GenerativeModel(self.model)
        elif self.provider == "openai":
            import openai
            openai.api_key = self.api_key
        elif self.provider == "anthropic":
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)
        elif self.provider == "ollama":
            pass
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def generate(self, prompt: str, temperature: float = 0.2, max_tokens: int = 2000) -> str:
        try:
            if self.provider == "gemini":
                response = self.client.generate_content(prompt)
                return response.text
            elif self.provider == "openai":
                import openai
                response = openai.ChatCompletion.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return response.choices[0].message.content
            elif self.provider == "anthropic":
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.content[0].text
            elif self.provider == "ollama":
                resp = requests.post(
                    f"{config.OLLAMA_URL}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "temperature": temperature,
                        "options": {"num_predict": max_tokens}
                    },
                    timeout=300
                )
                if resp.status_code == 200:
                    return resp.json().get("response", "")
                else:
                    logger.error(f"Ollama error: {resp.status_code}")
                    return None
        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            return None