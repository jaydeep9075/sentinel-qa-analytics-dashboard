import logging
import time

import requests
from typing import List, Dict, Any
from .base import BaseConnector

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3


class APIConnector(BaseConnector):
    def __init__(self, url: str, method='GET', headers=None, params=None):
        self.url = url
        self.method = method
        self.headers = headers or {}
        self.params = params or {}

    def fetch(self) -> List[Dict[str, Any]]:
        """Return the raw JSON payload; the engine's structure normalizer
        relationalizes it (every nested record array preserved, not just
        the first list found)."""
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.request(
                    self.method, self.url,
                    headers=self.headers, params=self.params,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                data = response.json()
                return [{
                    'name': 'api_response',
                    'data': data,
                    'type': 'raw',
                    'metadata': {'url': self.url, 'method': self.method},
                }]
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    wait = 2 ** attempt
                    logger.warning(f"API request failed (attempt {attempt}/{MAX_RETRIES}), retrying in {wait}s: {exc}")
                    time.sleep(wait)
            except Exception as exc:
                # Non-retryable (HTTP 4xx/5xx after raise_for_status, bad JSON).
                raise
        raise last_exc
