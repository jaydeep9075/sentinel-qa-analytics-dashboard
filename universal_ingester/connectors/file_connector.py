import pandas as pd
import json
from pathlib import Path
from typing import List, Dict, Any
from .base import BaseConnector
import logging

logger = logging.getLogger(__name__)

class FileConnector(BaseConnector):
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

    def fetch(self) -> List[Dict[str, Any]]:
        ext = self.file_path.suffix.lower()
        if ext in ['.csv', '.xlsx', '.xls', '.json']:
            return self._read_structured()
        elif ext in ['.txt', '.pdf', '.png', '.jpg', '.jpeg']:
            return self._read_unstructured()
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    def _read_structured(self):
        if self.file_path.suffix == '.csv':
            df = pd.read_csv(self.file_path)
        elif self.file_path.suffix in ['.xlsx', '.xls']:
            df = pd.read_excel(self.file_path)
        elif self.file_path.suffix == '.json':
            df = pd.read_json(self.file_path)
        else:
            raise ValueError("Unsupported structured file")
        return [{
            'name': self.file_path.stem,
            'data': df,
            'type': 'structured',
            'metadata': {'file_path': str(self.file_path), 'rows': len(df)}
        }]

    def _read_unstructured(self):
        # For text-based files, extract text; for PDF/image, use OCR etc.
        text = self._extract_text()
        # Return as a single unstructured dataset (could split later)
        return [{
            'name': self.file_path.stem,
            'data': [{'text': text}],  # list of dicts, each with 'text' key
            'type': 'unstructured',
            'metadata': {'file_path': str(self.file_path)}
        }]

    def _extract_text(self):
        ext = self.file_path.suffix.lower()
        if ext == '.txt':
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return f.read()
        elif ext == '.pdf':
            # Use PyPDF2 for simple text extraction
            import PyPDF2
            with open(self.file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text = '\n'.join([page.extract_text() for page in reader.pages])
            return text
        elif ext in ['.png', '.jpg', '.jpeg']:
            # Use pytesseract for OCR
            from PIL import Image
            import pytesseract
            img = Image.open(self.file_path)
            text = pytesseract.image_to_string(img)
            return text
        else:
            raise ValueError("Unsupported unstructured file")