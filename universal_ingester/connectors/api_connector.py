import logging
import time

import requests
from typing import List, Dict, Any, Optional
from .base import BaseConnector

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3


class APIConnector(BaseConnector):
    def __init__(self, url: str, method='GET', headers=None, params=None, json_body=None):
        self.url = url
        self.method = method
        self.headers = headers or {}
        self.params = params or {}
        self.json_body = json_body

    def _request(self, timeout: float = REQUEST_TIMEOUT_SECONDS) -> requests.Response:
        kwargs: Dict[str, Any] = dict(
            headers=self.headers, params=self.params, timeout=timeout,
        )
        if self.json_body is not None:
            kwargs["json"] = self.json_body
        response = requests.request(self.method, self.url, **kwargs)
        response.raise_for_status()
        return response

    def test_connection(self) -> Dict[str, Any]:
        """A single-attempt probe (no retries) used by the UI's 'Test
        Connection' step - reports status/content-type/a body preview
        without committing to a full ingestion run."""
        response = self._request(timeout=10)
        content_type = response.headers.get("content-type", "")
        preview = response.text[:500]
        parsed_ok = True
        try:
            response.json()
        except ValueError:
            parsed_ok = False
        return {
            "success": True,
            "status_code": response.status_code,
            "content_type": content_type,
            "is_json": parsed_ok,
            "preview": preview,
        }

    def fetch(self) -> List[Dict[str, Any]]:
        """Return the raw JSON payload; the engine's structure normalizer
        relationalizes it (every nested record array preserved, not just
        the first list found)."""
        last_exc: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._request()
                try:
                    data = response.json()
                except ValueError as exc:
                    content_type = response.headers.get("content-type", "unknown")
                    raise ValueError(
                        f"Response was not valid JSON (content-type: {content_type}): {exc}"
                    ) from exc
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
            except Exception:
                # Non-retryable (HTTP 4xx/5xx after raise_for_status, bad JSON).
                raise
        raise last_exc
