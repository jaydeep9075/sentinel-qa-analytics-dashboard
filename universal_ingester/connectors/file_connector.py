import pandas as pd
import json
from pathlib import Path
from typing import List, Dict, Any
from .base import BaseConnector
import logging
import csv

logger = logging.getLogger(__name__)

class FileConnector(BaseConnector):
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

    def fetch(self) -> List[Dict[str, Any]]:
        ext = self.file_path.suffix.lower()
        if ext in ['.csv', '.tsv', '.xlsx', '.xls', '.json', '.jsonl', '.ndjson', '.parquet', '.xml']:
            try:
                return self._read_structured()
            except Exception as exc:
                logger.warning(f"Structured parse failed for {self.file_path}: {exc}; falling back to unstructured")
                return self._read_unstructured()
        if ext in ['.txt', '.log', '.md', '.pdf', '.png', '.jpg', '.jpeg', '.yaml', '.yml']:
            return self._read_unstructured()

        # Unknown extension: try structured first, then unstructured as fallback.
        try:
            return self._read_structured()
        except Exception:
            return self._read_unstructured()

    def _read_structured(self):
        suffix = self.file_path.suffix.lower()
        if suffix == '.csv':
            df = pd.read_csv(self.file_path)
        elif suffix == '.tsv':
            df = pd.read_csv(self.file_path, sep='\t')
        elif suffix in ['.xlsx', '.xls']:
            df = pd.read_excel(self.file_path)
        elif suffix == '.json':
            with open(self.file_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            if isinstance(payload, list):
                df = pd.DataFrame(payload)
            elif isinstance(payload, dict):
                list_key = next((k for k, v in payload.items() if isinstance(v, list)), None)
                if list_key:
                    df = pd.DataFrame(payload[list_key])
                else:
                    df = pd.DataFrame([payload])
            else:
                df = pd.DataFrame([{"value": payload}])
        elif suffix in ['.jsonl', '.ndjson']:
            rows = []
            with open(self.file_path, 'r', encoding='utf-8') as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        obj = json.loads(ln)
                        rows.append(obj if isinstance(obj, dict) else {"value": obj})
                    except Exception:
                        rows.append({"raw_line": ln})
            df = pd.DataFrame(rows)
        elif suffix == '.parquet':
            df = pd.read_parquet(self.file_path)
        elif suffix == '.xml':
            df = pd.read_xml(self.file_path)
        else:
            # Last-chance attempt as CSV with auto-sniffing.
            with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                sample = f.read(4096)
            try:
                dialect = csv.Sniffer().sniff(sample)
                sep = dialect.delimiter
            except Exception:
                sep = ','
            df = pd.read_csv(self.file_path, sep=sep, on_bad_lines='skip')

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
        elif ext in ['.log', '.md', '.yaml', '.yml']:
            with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
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