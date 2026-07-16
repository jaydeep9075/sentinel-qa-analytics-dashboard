"""
Production-grade RAG service with prompt analysis and response validation.
"""

import json
import logging
import os
import re
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class PromptAnalyzer:
    """Analyze user prompts to extract intent, context, and queries."""

    INTENT_KEYWORDS = {
        'count': ['how many', 'total', 'number of', 'count'],
        'trend': ['trend', 'over time', 'change', 'increase', 'decrease', 'growth'],
        'comparison': ['compare', 'vs', 'versus', 'difference', 'better', 'worse'],
        'top': ['top', 'highest', 'lowest', 'best', 'worst', 'most', 'least'],
        'distribution': ['distribution', 'breakdown', 'split', 'percentage'],
        'summary': ['summary', 'overview', 'snapshot', 'overall', 'general'],
        'detail': ['details', 'specifically', 'exactly', 'which', 'what'],
    }

    def __init__(self, schema_info: Optional[Dict[str, Any]] = None):
        self.schema_info = schema_info or {}
        self.fields = self.schema_info.get('fields', {})

    def analyze(self, prompt: str, data_type: str = "test") -> Dict[str, Any]:
        """
        Analyze prompt to extract intent and generate optimized query.

        Returns:
        {
            'intent': 'count|trend|comparison|top|distribution|summary|detail',
            'entities': ['field1', 'field2', ...],
            'filters': {'field': 'value', ...},
            'aggregations': ['count', 'sum', 'avg', ...],
            'sort': {'field': 'asc/desc'},
            'query_type': 'simple_filter|aggregation|time_series|join',
            'confidence': 0.0-1.0,
            'optimization_hints': [...]
        }
        """

        prompt_lower = prompt.lower()

        # Detect intent
        intent = self._detect_intent(prompt_lower)

        # Extract entities (field names, values)
        entities = self._extract_entities(prompt_lower)

        # Extract filters
        filters = self._extract_filters(prompt_lower)

        # Determine aggregations needed
        aggregations = self._determine_aggregations(intent, entities)

        # Determine sort order
        sort = self._determine_sort(intent, prompt_lower)

        # Determine query type
        query_type = self._determine_query_type(intent, aggregations, filters)

        # Get optimization hints
        hints = self._get_optimization_hints(intent, entities, aggregations)

        confidence = self._calculate_confidence(intent, entities, filters)

        return {
            'intent': intent,
            'entities': list(set(entities)),
            'filters': filters,
            'aggregations': aggregations,
            'sort': sort,
            'query_type': query_type,
            'confidence': confidence,
            'optimization_hints': hints,
            'original_prompt': prompt,
            'data_type': data_type,
        }

    def _detect_intent(self, prompt_lower: str) -> str:
        """Detect user's intent from prompt."""
        for intent, keywords in self.INTENT_KEYWORDS.items():
            if any(kw in prompt_lower for kw in keywords):
                return intent
        return 'summary'

    def _extract_entities(self, prompt_lower: str) -> List[str]:
        """Extract field names and values from prompt."""
        entities = []

        # Known field patterns (based on Allure/test data)
        field_patterns = {
            'status': ['passed', 'failed', 'skipped', 'pending', 'broken'],
            'module': ['module', 'feature', 'suite', 'component'],
            'project': ['project', 'app', 'service', 'component'],
            'platform': ['desktop', 'mobile', 'web', 'api'],
            'duration': ['duration', 'time', 'execution', 'latency'],
            'error': ['error', 'failure', 'issue', 'problem'],
        }

        for field, values in field_patterns.items():
            if any(v in prompt_lower for v in values):
                entities.append(field)

        return entities

    def _extract_filters(self, prompt_lower: str) -> Dict[str, Any]:
        """Extract filter conditions from prompt."""
        filters = {}

        # Status filters
        statuses = {
            'passed': prompt_lower.count('passed') or prompt_lower.count('pass'),
            'failed': prompt_lower.count('failed') or prompt_lower.count('fail'),
            'skipped': prompt_lower.count('skipped'),
        }
        if any(statuses.values()):
            for status, count in statuses.items():
                if count > 0:
                    filters['status'] = status
                    break

        # Module/Feature filters
        if 'auth' in prompt_lower:
            filters['module'] = 'auth'
        elif 'login' in prompt_lower:
            filters['module'] = 'login'
        elif 'checkout' in prompt_lower:
            filters['module'] = 'checkout'

        return filters

    def _determine_aggregations(self, intent: str, entities: List[str]) -> List[str]:
        """Determine what aggregations to apply."""
        aggregations = []

        if intent in ('count', 'summary', 'distribution'):
            aggregations.append('count')

        if 'duration' in entities:
            aggregations.extend(['avg', 'sum', 'min', 'max'])

        if intent == 'trend':
            aggregations.append('time_series')

        return list(set(aggregations)) if aggregations else ['count']

    def _determine_sort(self, intent: str, prompt_lower: str) -> Optional[Dict[str, str]]:
        """Determine sort order."""
        if 'top' in prompt_lower or 'highest' in prompt_lower:
            return {'field': 'count', 'direction': 'desc'}

        if 'lowest' in prompt_lower or 'bottom' in prompt_lower:
            return {'field': 'count', 'direction': 'asc'}

        if 'latest' in prompt_lower or 'recent' in prompt_lower:
            return {'field': 'timestamp', 'direction': 'desc'}

        return None

    def _determine_query_type(self, intent: str, aggregations: List[str], filters: Dict) -> str:
        """Determine the type of query needed."""
        if not aggregations or aggregations == ['count']:
            if filters:
                return 'simple_filter'
            return 'simple_filter'

        if 'time_series' in aggregations:
            return 'time_series'

        if len(aggregations) > 1 or any(a in aggregations for a in ['avg', 'sum']):
            return 'aggregation'

        return 'aggregation'

    def _get_optimization_hints(self, intent: str, entities: List[str], aggregations: List[str]) -> List[str]:
        """Get optimization hints for query execution."""
        hints = []

        if intent == 'trend':
            hints.append('Use time-based bucketing for efficiency')
            hints.append('Consider pre-aggregated time-series if available')

        if 'duration' in entities:
            hints.append('Index duration field for faster aggregation')
            hints.append('Consider percentile aggregation if checking outliers')

        if len(aggregations) > 2:
            hints.append('Use materialized aggregations if available')

        if intent in ('top', 'distribution'):
            hints.append('Limit result set for faster response')

        return hints

    def _calculate_confidence(self, intent: str, entities: List[str], filters: Dict) -> float:
        """Calculate confidence in analysis."""
        confidence = 0.6

        # More entities = higher confidence
        confidence += min(len(entities) * 0.1, 0.2)

        # More filters = higher confidence
        confidence += min(len(filters) * 0.1, 0.2)

        # Intent detection adds confidence
        if intent != 'summary':
            confidence += 0.05

        return min(confidence, 1.0)


class ResponseValidator:
    """Validate and enhance RAG responses."""

    def __init__(self, schema_info: Optional[Dict[str, Any]] = None):
        self.schema_info = schema_info or {}

    def validate_response(
        self,
        response: str,
        prompt: str,
        analysis: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Validate response quality and add metadata.

        Returns:
        {
            'response': str,
            'is_valid': bool,
            'confidence': 0.0-1.0,
            'validation_checks': {
                'has_numbers': bool,
                'has_context': bool,
                'is_complete': bool,
                'mentions_limitations': bool,
            },
            'enhancement_suggestions': [...],
            'execution_time_ms': float,
            'data_points_used': int,
        }
        """

        validation_checks = {
            'has_numbers': self._check_has_numbers(response),
            'has_context': self._check_has_context(response, prompt),
            'is_complete': self._check_completeness(response, analysis),
            'mentions_limitations': self._check_mentions_limitations(response),
        }

        suggestions = self._get_enhancement_suggestions(response, validation_checks, analysis)

        confidence = self._calculate_response_confidence(validation_checks, analysis)

        is_valid = validation_checks['has_context'] and validation_checks['is_complete']

        return {
            'response': response,
            'is_valid': is_valid,
            'confidence': round(confidence, 2),
            'validation_checks': validation_checks,
            'enhancement_suggestions': suggestions,
            'execution_time_ms': context.get('execution_time_ms', 0) if context else 0,
            'data_points_used': context.get('data_points_used', 0) if context else 0,
            'validated_at': datetime.now(timezone.utc).isoformat(),
        }

    def _check_has_numbers(self, response: str) -> bool:
        """Check if response contains numerical data."""
        return bool(re.search(r'\d+', response))

    def _check_has_context(self, response: str, prompt: str) -> bool:
        """Check if response addresses the user's prompt."""
        # Extract key terms from prompt
        key_terms = set(prompt.lower().split())
        response_lower = response.lower()

        matching_terms = sum(1 for term in key_terms if term in response_lower)
        return matching_terms >= max(2, len(key_terms) // 2)

    def _check_completeness(self, response: str, analysis: Dict[str, Any]) -> bool:
        """Check if response is complete for the intended analysis."""
        # Check if response length is reasonable
        if len(response) < 20:
            return False

        intent = analysis.get('intent', 'summary')

        # For aggregation intents, ensure multiple data points
        if intent in ('comparison', 'distribution', 'top'):
            return response.count('\n') > 0 or ',' in response

        return len(response) > 50

    def _check_mentions_limitations(self, response: str) -> bool:
        """Check if response mentions any limitations or caveats."""
        limitation_words = ['however', 'note', 'limitation', 'caveat', 'missing', 'partial']
        return any(word in response.lower() for word in limitation_words)

    def _get_enhancement_suggestions(
        self,
        response: str,
        checks: Dict[str, bool],
        analysis: Dict[str, Any]
    ) -> List[str]:
        """Get suggestions to enhance the response."""
        suggestions = []

        if not checks['has_numbers']:
            suggestions.append('Consider including specific metrics/numbers')

        if not checks['mentions_limitations']:
            suggestions.append('Consider mentioning data scope/limitations for transparency')

        if not checks['is_complete'] and analysis.get('intent', 'summary') in ('comparison', 'distribution'):
            suggestions.append('Consider breaking down the response with multiple examples')

        if len(response) < 100 and analysis.get('confidence', 0.5) < 0.7:
            suggestions.append('Response may be too brief given analysis uncertainty - consider elaborating')

        return suggestions

    def _calculate_response_confidence(self, checks: Dict[str, bool], analysis: Dict[str, Any]) -> float:
        """Calculate overall response confidence."""
        base_confidence = analysis.get('confidence', 0.6)

        # Adjust based on validation checks
        if checks['has_context']:
            base_confidence += 0.1
        if checks['has_numbers']:
            base_confidence += 0.1
        if checks['is_complete']:
            base_confidence += 0.1
        if checks['mentions_limitations']:
            base_confidence += 0.05

        return min(base_confidence, 1.0)


class RAGService:
    """Main RAG service combining prompt analysis, LanceDB search, and response validation."""

    def __init__(self, lancedb_connection=None, schema_info: Optional[Dict[str, Any]] = None):
        self.lancedb = lancedb_connection
        self.schema_info = schema_info or {}
        self.analyzer = PromptAnalyzer(schema_info)
        self.validator = ResponseValidator(schema_info)

    def generate_response(
        self,
        prompt: str,
        data_type: str = "test",
        use_llm_callback=None,
    ) -> Dict[str, Any]:
        """
        Generate production-grade response with analysis and validation.

        Args:
            prompt: User query
            data_type: Type of data (allure_test, generic_json, etc.)
            use_llm_callback: Function to call LLM for response generation

        Returns:
        {
            'response': str,
            'analysis': {...},
            'validation': {...},
            'metadata': {...},
            'execution_time_ms': float,
        }
        """

        import time
        start_time = time.time()

        # 1. Analyze prompt
        analysis = self.analyzer.analyze(prompt, data_type)
        logger.info(f"Prompt analysis: intent={analysis['intent']}, confidence={analysis['confidence']}")

        # 2. Search LanceDB (if available)
        search_results = None
        data_context = None
        if self.lancedb:
            search_results = self._search_lancedb(prompt, analysis)
            data_context = self._format_context(search_results, analysis)

        # 3. Generate response with LLM
        response = ""
        if use_llm_callback:
            response = use_llm_callback(prompt, data_context, analysis)
        else:
            response = self._generate_fallback_response(prompt, analysis, search_results)

        # 4. Validate response
        validation = self.validator.validate_response(
            response,
            prompt,
            analysis,
            context={
                'execution_time_ms': (time.time() - start_time) * 1000,
                'data_points_used': len(search_results) if search_results else 0,
            }
        )

        return {
            'response': response,
            'analysis': analysis,
            'validation': validation,
            'metadata': {
                'data_type': data_type,
                'search_results_count': len(search_results) if search_results else 0,
                'has_lancedb_context': bool(self.lancedb),
            },
            'execution_time_ms': (time.time() - start_time) * 1000,
        }

    def _search_lancedb(self, prompt: str, analysis: Dict[str, Any]) -> Optional[List[Dict]]:
        """Search LanceDB for relevant documents."""
        if not self.lancedb:
            return None

        try:
            # TODO: Implement embedding + search
            # For now, return None
            return None
        except Exception as e:
            logger.warning(f"LanceDB search failed: {e}")
            return None

    def _format_context(self, search_results: Optional[List[Dict]], analysis: Dict[str, Any]) -> str:
        """Format search results as context for LLM."""
        if not search_results:
            return ""

        context_lines = ["Context from data:", ""]
        for result in search_results[:10]:
            text = result.get('text', str(result))
            context_lines.append(f"- {text[:200]}")

        return "\n".join(context_lines)

    def _generate_fallback_response(
        self,
        prompt: str,
        analysis: Dict[str, Any],
        search_results: Optional[List[Dict]]
    ) -> str:
        """Generate response without LLM (fallback)."""
        intent = analysis['intent']
        entities = analysis.get('entities', [])
        filters = analysis.get('filters', {})

        if intent == 'count':
            return "Based on the analysis, I would need to query the database to provide an accurate count. Please ensure the data is properly ingested."

        if intent == 'trend':
            return "To analyze trends, I need access to time-series data. Ensure the data contains timestamp information for trend analysis."

        if intent == 'comparison':
            return "For comparison analysis, the system would compare the specified entities. Please provide more specific criteria."

        return f"I understand you're asking about {', '.join(entities) if entities else 'your data'}. To provide a precise answer, I need to analyze the ingested data structure."
