"""File connector: reads files and hands data to the ingestion engine.

Connectors deliberately do NOT parse/normalize beyond loading bytes into a
basic Python/pandas representation — structure discovery, flattening,
chunking and storage decisions all live in the engine:

- JSON returns the *raw parsed payload* (type 'raw') so the engine's
  structure normalizer can preserve every nested array/object instead of
  the connector guessing which list matters.
- Tabular formats (CSV/TSV/JSONL/Excel/Parquet/XML) return DataFrames;
  large CSV/JSONL files stream as batch iterators so they never have to
  fit in memory.
- Text-like formats (txt/log/md/pdf/images) return extracted text as
  unstructured items; the engine chunks and embeds them.
"""

import pandas as pd
import json
import os
from pathlib import Path
from typing import List, Dict, Any
from .base import BaseConnector
import logging
import csv

logger = logging.getLogger(__name__)

# Files bigger than this stream in batches instead of loading whole.
STREAM_THRESHOLD_BYTES = int(os.getenv("INGEST_STREAM_THRESHOLD_BYTES", str(50 * 1024 * 1024)))
STREAM_BATCH_ROWS = int(os.getenv("INGEST_STREAM_BATCH_ROWS", "20000"))


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
        if ext in ['.txt', '.log', '.md', '.html', '.htm', '.pdf', '.png', '.jpg', '.jpeg', '.yaml', '.yml']:
            return self._read_unstructured()

        # Unknown extension: try structured first, then unstructured as fallback.
        try:
            return self._read_structured()
        except Exception:
            return self._read_unstructured()

    def _is_large(self) -> bool:
        try:
            return self.file_path.stat().st_size > STREAM_THRESHOLD_BYTES
        except Exception:
            return False

    def _read_structured(self):
        suffix = self.file_path.suffix.lower()
        base_meta = {'file_path': str(self.file_path)}

        if suffix in ['.csv', '.tsv']:
            sep = '\t' if suffix == '.tsv' else ','
            if self._is_large():
                return [{
                    'name': self.file_path.stem,
                    'data': None,
                    'data_iter': self._stream_csv(sep),
                    'type': 'structured',
                    'metadata': {**base_meta, 'streamed': True},
                }]
            df = self._read_delimited_csv(default_sep=sep)

        elif suffix in ['.xlsx', '.xls']:
            sheet_map = pd.read_excel(self.file_path, sheet_name=None)
            datasets = []
            for sheet, sdf in sheet_map.items():
                sdf = sdf if isinstance(sdf, pd.DataFrame) else pd.DataFrame(sdf)
                datasets.append({
                    'name': f"{self.file_path.stem}_{sheet}",
                    'data': sdf,
                    'type': 'structured',
                    'metadata': {**base_meta, 'sheet_name': str(sheet), 'rows': len(sdf)},
                })
            return datasets

        elif suffix == '.json':
            # Raw payload: the engine's structure normalizer decides how to
            # relationalize it — every nested record array is preserved,
            # not just the first list found.
            with open(self.file_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            return [{
                'name': self.file_path.stem,
                'data': payload,
                'type': 'raw',
                'metadata': base_meta,
            }]

        elif suffix in ['.jsonl', '.ndjson']:
            if self._is_large():
                return [{
                    'name': self.file_path.stem,
                    'data': None,
                    'data_iter': self._stream_jsonl(),
                    'type': 'structured',
                    'metadata': {**base_meta, 'streamed': True},
                }]
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
            return [{
                'name': self.file_path.stem,
                'data': rows,
                'type': 'raw',
                'metadata': base_meta,
            }]

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
            df = self._read_delimited_csv(default_sep=sep)

        return [{
            'name': self.file_path.stem,
            'data': df,
            'type': 'structured',
            'metadata': {**base_meta, 'rows': len(df)},
        }]

    def _stream_csv(self, sep: str):
        """Yield DataFrame batches so huge CSVs never load fully in memory."""
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
        for enc in encodings:
            try:
                reader = pd.read_csv(
                    self.file_path, sep=sep, encoding=enc,
                    on_bad_lines='skip', chunksize=STREAM_BATCH_ROWS,
                )
                for chunk in reader:
                    yield chunk
                return
            except UnicodeDecodeError:
                continue
            except Exception:
                raise

    def _stream_jsonl(self):
        rows = []
        with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    obj = json.loads(ln)
                    rows.append(obj if isinstance(obj, dict) else {"value": obj})
                except Exception:
                    rows.append({"raw_line": ln})
                if len(rows) >= STREAM_BATCH_ROWS:
                    yield pd.DataFrame(rows)
                    rows = []
        if rows:
            yield pd.DataFrame(rows)

    def _read_unstructured(self):
        # For text-based files, extract text; for PDF/image, use OCR etc.
        text = self._extract_text()
        return [{
            'name': self.file_path.stem,
            'data': [{'text': text}],  # list of dicts, each with 'text' key
            'type': 'unstructured',
            'metadata': {
                'file_path': str(self.file_path),
                'doc_type': self.file_path.suffix.lower().lstrip('.') or 'text',
            }
        }]

    def _extract_text(self):
        ext = self.file_path.suffix.lower()
        if ext in ['.txt', '.log', '.md', '.yaml', '.yml', '.html', '.htm']:
            return self._read_text_with_fallbacks()
        elif ext == '.pdf':
            # Best-effort PDF extraction with graceful fallback.
            try:
                import PyPDF2
                with open(self.file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    text = '\n'.join([(page.extract_text() or '') for page in reader.pages])
                text = text.strip()
                if text:
                    return text
            except Exception as exc:
                logger.warning(f"PyPDF2 extraction failed for {self.file_path}: {exc}")
            return f"[PDF extraction unavailable for {self.file_path.name}]"
        elif ext in ['.png', '.jpg', '.jpeg']:
            # Use pytesseract for OCR
            try:
                from PIL import Image
                import pytesseract
                img = Image.open(self.file_path)
                text = pytesseract.image_to_string(img)
                return text.strip() or f"[OCR produced empty text for {self.file_path.name}]"
            except Exception as exc:
                logger.warning(f"OCR failed for {self.file_path}: {exc}")
                return f"[Image OCR unavailable for {self.file_path.name}]"
        else:
            return self._read_text_with_fallbacks()

    def _read_delimited_csv(self, default_sep=','):
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
        last_exc = None
        for enc in encodings:
            try:
                return pd.read_csv(self.file_path, sep=default_sep, encoding=enc, on_bad_lines='skip')
            except Exception as exc:
                last_exc = exc
        if last_exc:
            raise last_exc
        return pd.read_csv(self.file_path, sep=default_sep, on_bad_lines='skip')

    def _read_text_with_fallbacks(self):
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
        for enc in encodings:
            try:
                with open(self.file_path, 'r', encoding=enc, errors='ignore') as f:
                    return f.read()
            except Exception:
                continue
        with open(self.file_path, 'r', errors='ignore') as f:
            return f.read()
