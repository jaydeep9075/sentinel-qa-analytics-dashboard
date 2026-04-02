from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseConnector(ABC):
    @abstractmethod
    def fetch(self) -> List[Dict[str, Any]]:
        """Return list of datasets. Each dataset is a dict with:
           - name: str
           - data: pd.DataFrame (for structured) or list of dicts (for unstructured)
           - type: 'structured' or 'unstructured'
           - metadata: dict
        """
        pass