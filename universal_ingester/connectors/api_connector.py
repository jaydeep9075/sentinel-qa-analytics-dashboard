import requests
import pandas as pd
from typing import List, Dict, Any
from .base import BaseConnector

class APIConnector(BaseConnector):
    def __init__(self, url: str, method='GET', headers=None, params=None):
        self.url = url
        self.method = method
        self.headers = headers or {}
        self.params = params or {}

    def fetch(self) -> List[Dict[str, Any]]:
        response = requests.request(self.method, self.url, headers=self.headers, params=self.params)
        response.raise_for_status()
        data = response.json()
        # Assume data is list of objects or a dict with a key containing list
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            # Try to find first list value
            for v in data.values():
                if isinstance(v, list):
                    df = pd.DataFrame(v)
                    break
            else:
                df = pd.DataFrame([data])
        else:
            df = pd.DataFrame([{'value': data}])

        return [{
            'name': 'api_response',
            'data': df,
            'type': 'structured',
            'metadata': {'url': self.url, 'method': self.method}
        }]