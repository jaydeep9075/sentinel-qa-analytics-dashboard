from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseIngestor(ABC):
    @abstractmethod
    def fetch_results(self) -> List[Dict[str, Any]]:
        """
        Fetch test results from a source.
        Returns a list of standardized dictionaries:
        {
            "uuid": str,
            "name": str,
            "module": str,
            "status": str (passed, failed, skipped, broken),
            "duration_sec": float,
            "error_msg": str,
            "timestamp": int (unix ms),
            "env": str,
            "tags": List[str]
        }
        """
        pass
