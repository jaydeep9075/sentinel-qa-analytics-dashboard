"""Runtime schema detection with Python heuristics + AI fallback."""

import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
import re

logger = logging.getLogger(__name__)


class RuntimeSchemaDetector:
    """Detect schema at runtime from sample records."""

    def __init__(self):
        self.ai_provider = None
        self.ai_model = None
        try:
            import os
            self.ai_provider = os.getenv("LLM_PROVIDER", "gemini")
            self.ai_model = os.getenv("LLM_MODEL", "gemini/gemini-2.5-flash")
        except Exception:
            pass

    def detect(
        self,
        records: List[Dict[str, Any]],
        data_context: str = "",
        sample_size: int = 20
    ) -> Dict[str, Any]:
        """
        Detect schema from records using Python heuristics + AI fallback.

        Args:
            records: List of data records (dicts)
            data_context: Context about data (e.g., "Allure test data")
            sample_size: Number of records to sample for detection

        Returns:
            {
                'fields': {
                    'field_name': {
                        'type': 'numeric|category|datetime|text',
                        'purpose': 'identifier|status|metric|timestamp',
                        'cardinality': int,
                        'sample_values': [...],
                        'confidence': 0.0-1.0
                    }
                },
                'data_type': 'allure_test|generic_json|...',
                'confidence': 0.0-1.0,
                'used_ai': bool
            }
        """
        if not records:
            return {
                "fields": {},
                "data_type": "unknown",
                "confidence": 0.0,
                "used_ai": False
            }

        sample = records[:min(sample_size, len(records))]
        fields_schema = {}
        used_ai = False

        # Get all unique field names
        all_fields = set()
        for record in sample:
            if isinstance(record, dict):
                all_fields.update(record.keys())

        # Detect each field
        for field_name in sorted(all_fields):
            values = []
            for record in sample:
                if isinstance(record, dict) and field_name in record:
                    val = record[field_name]
                    if val is not None and val != "":
                        values.append(val)

            if not values:
                continue

            # Python heuristics (Python-first approach)
            field_info = self._detect_field_python(field_name, values)

            # AI fallback if confidence too low
            if field_info["confidence"] < 0.7 and self.ai_provider:
                ai_info = self._detect_field_ai(field_name, values, data_context)
                if ai_info:
                    field_info = ai_info
                    used_ai = True

            fields_schema[field_name] = field_info

        # Detect overall data type
        data_type = self._detect_data_type(fields_schema, data_context)

        overall_confidence = sum(
            f.get("confidence", 0.5) for f in fields_schema.values()
        ) / len(fields_schema) if fields_schema else 0.0

        return {
            "fields": fields_schema,
            "data_type": data_type,
            "confidence": round(overall_confidence, 2),
            "used_ai": used_ai,
            "field_count": len(fields_schema),
            "sample_size": len(sample)
        }

    def _detect_field_python(
        self,
        field_name: str,
        values: List[Any]
    ) -> Dict[str, Any]:
        """Detect field type using Python heuristics (fast, no AI)."""

        # Check if all numeric
        numeric_count = 0
        for v in values:
            try:
                float(v)
                numeric_count += 1
            except (ValueError, TypeError):
                pass

        if numeric_count >= len(values) * 0.9:
            return {
                "type": "numeric",
                "purpose": self._infer_purpose_from_name(field_name, "numeric"),
                "cardinality": len(set(v for v in values if v)),
                "sample_values": values[:5],
                "confidence": 0.95
            }

        # Check if all datetime
        datetime_count = 0
        for v in values:
            if self._is_datetime(str(v)):
                datetime_count += 1

        if datetime_count >= len(values) * 0.8:
            return {
                "type": "datetime",
                "purpose": self._infer_purpose_from_name(field_name, "datetime"),
                "cardinality": len(set(v for v in values if v)),
                "sample_values": values[:5],
                "confidence": 0.9
            }

        # Check if categorical (low cardinality)
        unique_values = len(set(str(v) for v in values if v))
        cardinality_ratio = unique_values / len(values)

        if cardinality_ratio < 0.1 or unique_values < 20:
            return {
                "type": "category",
                "purpose": self._infer_purpose_from_name(field_name, "category"),
                "cardinality": unique_values,
                "sample_values": list(set(str(v) for v in values[:10] if v))[:5],
                "confidence": 0.85
            }

        # Default to text
        return {
            "type": "text",
            "purpose": self._infer_purpose_from_name(field_name, "text"),
            "cardinality": unique_values,
            "sample_values": values[:5],
            "confidence": 0.6
        }

    def _detect_field_ai(
        self,
        field_name: str,
        values: List[Any],
        data_context: str
    ) -> Optional[Dict[str, Any]]:
        """Detect field type using AI (fallback for ambiguous cases)."""
        try:
            import litellm
        except ImportError:
            logger.warning("litellm not available, skipping AI detection")
            return None

        import os
        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )

        if not api_key:
            logger.warning("No API key configured for AI schema detection")
            return None

        try:
            sample_str = ", ".join(str(v)[:50] for v in values[:5])
            prompt = (
                f"Analyze this field in {data_context}:\n"
                f"Field name: {field_name}\n"
                f"Sample values: {sample_str}\n\n"
                f"Respond with JSON: {{"
                f'"type": "numeric|category|datetime|text", '
                f'"purpose": "identifier|status|metric|timestamp|other"'
                f"}}"
            )

            kwargs = {
                "model": self.ai_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 200,
            }
            if api_key:
                kwargs["api_key"] = api_key

            resp = litellm.completion(**kwargs)
            content = resp.choices[0].message.content if resp and resp.choices else ""

            # Parse JSON response
            import re
            json_match = re.search(r'\{[^}]+\}', content)
            if json_match:
                result = json.loads(json_match.group())
                return {
                    "type": result.get("type", "text"),
                    "purpose": result.get("purpose", "other"),
                    "cardinality": len(set(str(v) for v in values if v)),
                    "sample_values": values[:5],
                    "confidence": 0.75,
                    "ai_detected": True
                }
        except Exception as e:
            logger.warning(f"AI schema detection failed for {field_name}: {e}")

        return None

    def _is_datetime(self, value_str: str) -> bool:
        """Check if string is datetime."""
        patterns = [
            r'^\d{4}-\d{2}-\d{2}',  # ISO date
            r'^\d{2}/\d{2}/\d{4}',  # US date
            r'^\d{10,13}$',  # Unix timestamp
            r'T\d{2}:\d{2}:\d{2}',  # ISO time
            r'\d{1,2}:\d{2}:\d{2}',  # HH:MM:SS
        ]
        return any(re.search(p, value_str) for p in patterns)

    def _infer_purpose_from_name(self, field_name: str, field_type: str) -> str:
        """Infer field purpose from name."""
        lower_name = field_name.lower()

        # Identifier patterns
        if any(x in lower_name for x in ["id", "uuid", "name", "title", "test_name"]):
            return "identifier"

        # Status patterns
        if any(x in lower_name for x in ["status", "state", "result", "outcome"]):
            return "status"

        # Metric patterns
        if any(x in lower_name for x in ["count", "duration", "size", "time", "ms", "sec", "seconds", "milliseconds"]):
            return "metric"

        # Timestamp patterns
        if any(x in lower_name for x in ["timestamp", "time", "date", "created", "executed", "start", "stop"]):
            return "timestamp"

        return "other"

    def _detect_data_type(self, fields_schema: Dict[str, Any], data_context: str) -> str:
        """Detect overall data type based on fields."""
        if not fields_schema:
            return "generic_json"

        field_names = set(fields_schema.keys())

        # Detect Allure test data
        if any(x in field_names for x in ["status", "test_name", "duration", "error"]):
            if any(x in field_names for x in ["module_name", "project_name"]):
                return "allure_test"

        # Generic JSON
        return "generic_json"
