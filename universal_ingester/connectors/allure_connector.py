import json
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any
from .base import BaseConnector
import logging

logger = logging.getLogger(__name__)

class AllureConnector(BaseConnector):
    def __init__(self, directory: str):
        self.directory = Path(directory)
        if not self.directory.exists():
            raise FileNotFoundError(f"Allure directory not found: {directory}")

    def fetch(self) -> List[Dict[str, Any]]:
        """Parse all *-result.json files and return a dataset."""
        result_files = list(self.directory.glob("*-result.json"))
        if not result_files:
            logger.warning(f"No Allure result files found in {self.directory}")
            return []

        rows = []
        for file_path in result_files:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Extract key fields
            test_name = data.get('name', '')
            status = data.get('status', '').lower()
            duration = data.get('time', {}).get('duration', 0)
            error = ''
            if status == 'failed':
                details = data.get('statusDetails', {})
                error = details.get('message', '') or details.get('trace', '')
            labels = data.get('labels', [])
            tags = [l['value'] for l in labels if l.get('name') == 'tag']
            suite = next((l['value'] for l in labels if l.get('name') == 'suite'), '')
            # Flatten steps (optional) – we might skip for now
            rows.append({
                'test_name': test_name,
                'status': status,
                'duration': duration / 1000 if duration else 0,  # convert ms to seconds
                'error': error,
                'suite': suite,
                'tags': ','.join(tags),
                'file': file_path.name,
            })

        df = pd.DataFrame(rows)
        logger.info(f"Loaded {len(df)} test results from Allure directory")
        return [{
            'name': 'allure_results',
            'data': df,
            'type': 'structured',
            'metadata': {'directory': str(self.directory)}
        }]