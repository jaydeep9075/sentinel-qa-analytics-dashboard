"""
Production-grade prompts for perfect RAG responses.
Handles all edge scenarios, complex requests, and failures gracefully.
Generic enough for ANY data domain while specific enough for accuracy.
"""


SYSTEM_PROMPT_TEMPLATE = """You are a production-grade data analysis expert. Your role is to answer questions accurately,
handle edge cases gracefully, and provide trustworthy analysis for {data_type} data.

CRITICAL INSTRUCTIONS:
1. Always answer the question directly first (one sentence summary)
2. Provide specific numbers/metrics - NEVER use vague terms like "many", "few", "significant"
3. ALWAYS mention data limitations: sample size, date range, missing values, data quality issues
4. If data is insufficient: clearly state what's needed and suggest alternatives
5. Handle ambiguous queries by clarifying your interpretation
6. For complex queries: break into sub-questions and answer each
7. Suggest follow-up analyses that would provide deeper insights
8. Use clear structure: Answer → Evidence → Caveats → Next Steps

EDGE CASE HANDLING:
- Empty/no data: "No data found for [criteria]. Suggestions: [alternatives]"
- Partial data: "Results based on [X%] of expected data. May underestimate..."
- Ambiguous query: "Interpreting your question as: [interpretation]. If you meant [alternative], let me know."
- Multiple interpretations: List all valid interpretations and answer the most likely
- Outliers/anomalies: Always flag unusual patterns or extreme values
- New/unknown fields: Explain what the field represents and how it relates to the query

RESPONSE FORMAT:
1. Direct answer (1 sentence)
2. Supporting evidence (specific numbers, not percentages alone)
3. Data quality/limitation note
4. Relevant context or patterns
5. Suggested next analysis
6. Confidence assessment (high/medium/low and why)

Data Schema Available:
{schema_context}

Remember: Production accuracy > brevity. Better to be thorough than terse."""


PROMPT_ANALYSIS_TEMPLATE = """Analyze this user query and extract all actionable information.
Handle edge cases: ambiguous queries, missing context, impossible requests, etc.

Query: "{query}"
Data Type: {data_type}
Available Fields: {available_fields}

ANALYSIS GUIDELINES:
- If query is ambiguous: list ALL possible interpretations with confidence for each
- If query requires missing fields: identify what's needed and suggest alternatives
- If query is too broad: suggest narrowing down (date range, specific category, etc)
- If query is impossible with current data: explain clearly what would be needed
- Handle typos/misspellings: suggest correct field names
- Handle "all data" requests: note performance implications, suggest sampling/filtering

Respond in this EXACT JSON format (this is strict, validate JSON syntax):
{{
  "intent": "count|trend|comparison|top|distribution|summary|detail|error|clarification",
  "confidence": 0.0-1.0,
  "is_ambiguous": true/false,
  "is_executable": true/false,
  "requires_aggregation": true/false,
  "recommended_visualizations": ["chart1", "chart2"],
  "key_metrics": ["metric1", "metric2"],
  "suggested_filters": {{"field": "value"}},
  "clarification_needed": true/false,
  "clarification_questions": ["question1", "question2"],
  "execution_notes": "any important notes about how query will be executed",
  "limitations": "what might limit accuracy of results",
  "error_message": "if is_executable=false, explain why",
  "alternative_queries": ["if ambiguous, list alternatives"]
}}

IMPORTANT:
- confidence must reflect likelihood of accurate results (low if ambiguous/unclear)
- Be conservative with high confidence - only use 0.8+ if query is crystal clear
- Always populate 'execution_notes' and 'limitations' even if empty
- If anything is unclear, set clarification_needed=true with specific questions"""


RESPONSE_VALIDATION_TEMPLATE = """Strictly validate this data analysis response. Be a critical reviewer.
Production responses MUST meet high standards. Reject poor quality.

Original Query: "{query}"
Response: "{response}"
Data Type: {data_type}

VALIDATION CHECKLIST (all must pass for is_valid=true):
1. ✓ Directly answers the question in first sentence?
2. ✓ Includes specific numbers (NOT vague: "many", "few", "significant")?
3. ✓ Mentions data limitations (scope, missing data, quality issues)?
4. ✓ Explains any assumptions or interpretations made?
5. ✓ Provides context (e.g., "90% pass rate vs 85% last week")?
6. ✓ Acknowledges confidence/uncertainty if appropriate?
7. ✓ Suggests next steps or follow-up analysis?
8. ✓ Uses correct data types (dates, percentages, counts)?
9. ✓ No contradictions or logical errors?
10. ✓ Professional tone, appropriate for business use?

FAILURE MODES (auto-reject):
- Response doesn't answer the query → is_valid=false
- No numbers provided → is_valid=false
- Confabulated data not in source → is_valid=false
- Claims high confidence but insufficient evidence → is_valid=false
- Ignores obvious data limitations → is_valid=false

Respond in EXACT JSON format:
{{
  "is_valid": true/false,
  "quality_score": 0-100,
  "validation_results": {{
    "answers_query": true/false,
    "has_numbers": true/false,
    "mentions_limitations": true/false,
    "is_complete": true/false,
    "has_confidence": true/false,
    "no_contradictions": true/false,
    "professional_tone": true/false
  }},
  "critical_issues": ["critical issue 1", "critical issue 2"],
  "improvements_needed": ["improvement 1", "improvement 2"],
  "confidence_in_validation": 0.0-1.0,
  "rejection_reason": "if is_valid=false, explain why",
  "overall_feedback": "summary of validation result"
}}

Scoring guide:
- 90-100: Excellent, production-ready
- 80-89: Good, minor improvements suggested
- 70-79: Acceptable, needs improvements
- <70: Poor, should be rejected or heavily revised

Be harsh. Poor answers damage user trust. Better to reject than accept mediocre."""


ALLURE_CONTEXT_TEMPLATE = """Test Execution Data Schema:

Core Fields:
- test_name: Full name/identifier of the test
- status: passed|failed|skipped|pending
- duration_seconds: Execution time in seconds
- error_message: Failure details if status=failed
- module_name: Feature/module being tested
- project_name: Project/component name
- platform_type: desktop|mobile|web|api
- executed_at: Timestamp of test execution

Aggregation Examples:
- Pass rate: COUNT(status='passed') / COUNT(status IN ('passed','failed'))
- Slowest tests: ORDER BY duration_seconds DESC LIMIT 10
- Failures by module: GROUP BY module_name WHERE status='failed'
- Trend analysis: GROUP BY DATE(executed_at) ORDER BY executed_at

When analyzing test data:
1. Always mention pass/fail counts, not just rates
2. Highlight flaky tests (same test with different outcomes)
3. Note performance anomalies (unusually slow tests)
4. Suggest areas for improvement
5. Differentiate between different modules/platforms
"""


GENERIC_JSON_CONTEXT_TEMPLATE = """Generic JSON Data Schema:

Detected Fields:
{fields_description}

Analysis Guidelines:
1. Understand field purposes (identifier, metric, status, timestamp)
2. Group by categorical fields (status, type, category)
3. Aggregate numeric fields (sum, avg, count, min, max)
4. Use timestamps for trend analysis
5. Show examples from actual data when possible

Response Quality Checklist:
- Specific to the user's question
- Includes concrete numbers/examples
- Mentions data scope and limitations
- Suggests related insights
- Properly formatted for readability
"""


CHART_GENERATION_PROMPT = """Generate a chart specification from this query:

Query: "{query}"
Data Type: {data_type}
Fields Available: {fields}

Provide chart specification in JSON:
{{
  "chart_type": "line|bar|pie|scatter|histogram",
  "title": "Chart title reflecting the query",
  "x_axis": {{"field": "...", "label": "..."}},
  "y_axis": {{"field": "...", "aggregation": "sum|avg|count", "label": "..."}},
  "groupBy": ["field1"] or null,
  "filters": {{"field": "value"}} or {{}},
  "sort": {{"field": "...", "direction": "asc|desc"}} or null,
  "expected_data_points": integer,
  "recommendation": "Why this chart type is best"
}}

Choose chart type based on data type:
- Time series → line chart
- Categories with values → bar chart
- Part-to-whole → pie chart
- Correlations → scatter plot
- Distributions → histogram
"""


def get_system_prompt(data_type: str, schema_info: dict) -> str:
    """Generate system prompt for specific data type."""
    schema_context = _format_schema_context(data_type, schema_info)

    return SYSTEM_PROMPT_TEMPLATE.format(
        data_type=data_type,
        schema_context=schema_context
    )


def _format_schema_context(data_type: str, schema_info: dict) -> str:
    """Format schema information for prompt context."""
    if data_type == 'allure_test':
        return ALLURE_CONTEXT_TEMPLATE

    fields = schema_info.get('fields', {})
    if not fields:
        return "No schema information available."

    fields_desc = "\n".join([
        f"- {name}: {info.get('type', 'unknown')} ({info.get('purpose', 'unknown')})"
        for name, info in fields.items()
    ])

    return GENERIC_JSON_CONTEXT_TEMPLATE.format(
        fields_description=fields_desc
    )


def get_analysis_prompt(query: str, data_type: str, available_fields: list) -> str:
    """Generate prompt for query analysis."""
    return PROMPT_ANALYSIS_TEMPLATE.format(
        query=query,
        data_type=data_type,
        available_fields=", ".join(available_fields)
    )


def get_validation_prompt(query: str, response: str, data_type: str) -> str:
    """Generate prompt for response validation."""
    return RESPONSE_VALIDATION_TEMPLATE.format(
        query=query,
        response=response,
        data_type=data_type
    )


def get_chart_prompt(query: str, data_type: str, fields: list) -> str:
    """Generate prompt for chart generation."""
    return CHART_GENERATION_PROMPT.format(
        query=query,
        data_type=data_type,
        fields=", ".join(fields)
    )


# Response Templates
RESPONSE_TEMPLATES = {
    'count': """Based on the {data_type} data:

**{metric}**: {value}

{details}

{limitations}

Would you like to see a breakdown by {dimension}?""",

    'trend': """Test execution trend for {period}:

{chart_description}

**Key Findings:**
- {finding1}
- {finding2}
- {finding3}

{limitations}

Consider monitoring for unusual spikes or drops.""",

    'comparison': """Comparing {entity1} vs {entity2}:

| Metric | {entity1} | {entity2} | Difference |
|--------|-----------|-----------|------------|
{comparison_rows}

**Winner**: {winner_entity}

{analysis}

{limitations}""",

    'top': """{metric} ranking:

{ranked_list}

**Notable patterns:**
- {pattern1}
- {pattern2}

{limitations}

Want details on any specific item?""",

    'distribution': """Distribution of {field}:

{distribution_data}

**Summary:**
- Most common: {most_common}
- Least common: {least_common}
- Variety: {variety_metric}

{limitations}

Suggested grouping: {suggested_grouping}""",

    'error': """Unable to answer the question completely.

**Issue**: {error_message}

**What I need**: {missing_data}

**Workaround**: {suggested_workaround}

Please provide the missing information or rephrase your question.""",
}


def format_response(template_type: str, **kwargs) -> str:
    """Format response using template."""
    template = RESPONSE_TEMPLATES.get(template_type, RESPONSE_TEMPLATES['error'])

    try:
        return template.format(**kwargs)
    except KeyError as e:
        return f"Error formatting response: missing field {e}"


# Validation Rules
VALIDATION_RULES = {
    'minimum_length': 50,  # Minimum response length
    'requires_numbers': True,  # Must include specific metrics
    'requires_context': True,  # Must relate to original query
    'requires_limitations': True,  # Must mention data limitations
    'requires_structure': True,  # Must be well-organized
}


def validate_response_quality(response: str, rules: dict = None) -> dict:
    """Validate response against quality rules."""
    rules = rules or VALIDATION_RULES

    checks = {
        'length_ok': len(response) >= rules.get('minimum_length', 50),
        'has_numbers': any(c.isdigit() for c in response),
        'is_structured': '\n' in response or '|' in response,
        'mentions_limitations': any(
            word in response.lower()
            for word in ['however', 'note', 'limitation', 'caveat', 'missing', 'partial']
        ),
    }

    quality_score = sum(checks.values()) / len(checks) * 100

    return {
        'checks': checks,
        'quality_score': round(quality_score),
        'is_valid': all(checks.values()),
        'issues': [k for k, v in checks.items() if not v],
    }


# ==================== EDGE CASE & ERROR HANDLING PROMPTS ====================

ERROR_HANDLING_PROMPT = """Handle this error gracefully and help the user:

Error Type: {error_type}
Error Message: {error_message}
User Query: "{user_query}"
Context: {context}

RESPONSE STRATEGY BY ERROR TYPE:

If "no_data":
  - Explain what was searched for
  - Suggest filtering options to find data
  - Recommend alternative queries
  - Offer to check data availability

If "ambiguous_query":
  - List all possible interpretations
  - Ask which one they meant
  - Provide answers for the most likely interpretation
  - Show how different interpretations would change results

If "insufficient_data":
  - Quantify what's missing (e.g., "only 10% of expected data")
  - Explain impact on accuracy
  - Provide preliminary results with caveats
  - Suggest what would make results more reliable

If "data_quality":
  - Identify specific quality issues
  - Quantify impact (e.g., "20% of records have missing values")
  - Explain what was done to handle it
  - Suggest improvements for future data

If "timeout/performance":
  - Apologize for the delay
  - Suggest narrowing the query
  - Offer to run partial analysis
  - Provide example of more focused query

RESPONSE FORMAT:
1. Acknowledge the error clearly
2. Explain what went wrong in simple terms
3. Provide what information IS available
4. Suggest concrete next steps
5. Offer alternative approaches

TONE: Helpful, not apologetic. Empower user with options."""


COMPLEX_QUERY_PROMPT = """Handle this complex, multi-part query methodically:

Query: "{query}"
Complexity Type: {complexity_type}

HANDLING STRATEGIES:

If "multi-part" (asking about 3+ different things):
  ✓ Break into sub-questions
  ✓ Answer each independently
  ✓ Show how they relate to each other
  ✓ Provide integrated summary

If "temporal" (asking about changes over time):
  ✓ Show progression with dates
  ✓ Calculate period-over-period changes
  ✓ Identify turning points
  ✓ Extrapolate cautiously (note uncertainty)

If "hierarchical" (comparing at multiple levels):
  ✓ Start with top-level summary
  ✓ Drill down to next level
  ✓ Show how parts relate to whole
  ✓ Flag outliers or anomalies

If "correlation/causation":
  ✓ Show the correlation clearly
  ✓ NEVER imply causation without evidence
  ✓ Suggest confounding factors
  ✓ Recommend additional analysis needed

If "forecasting/projection":
  ✓ Use only historical patterns shown in data
  ✓ State assumptions explicitly
  ✓ Provide confidence interval if possible
  ✓ Warn about dangers of extrapolation

RESPONSE FORMAT:
1. Main finding (direct answer)
2. Supporting evidence (broken down clearly)
3. Assumptions made
4. Caveats and limitations
5. What would make this more accurate"""


AMBIGUITY_RESOLUTION_PROMPT = """Resolve ambiguity in this query intelligently:

Ambiguous Query: "{query}"
Possible Interpretations: {interpretations}
Available Data: {available_fields}

FOR EACH INTERPRETATION:
1. Explain what it means
2. Show what would be answered
3. Rate likelihood (high/medium/low)
4. Identify if it's even possible with current data

RESPONSE APPROACH:
- Most likely interpretation: Answer it fully
- Other interpretations: Mention briefly with confidence score
- If unclear which is intended: Ask clarifying question
- Never guess - always acknowledge ambiguity

CLARIFYING QUESTIONS TEMPLATE:
"I see your question could mean:
1. [Interpretation 1] - most likely based on context
2. [Interpretation 2] - if you meant X instead
3. [Interpretation 3] - if you're asking about Y

Which did you intend? I'll give you the exact analysis you need."""


FALLBACK_RESPONSE_TEMPLATE = """When you cannot provide a full answer, use this template:

Query: "{query}"
Reason for Fallback: {reason}

FALLBACK RESPONSE STRUCTURE:
1. "I can partially answer your question about [aspect]:"
2. [Provide what IS available]
3. "I cannot answer [missing aspect] because:"
   - [Specific limitation]
   - [What data is needed]
   - [Suggest workaround]
4. "To get a complete answer, you could:"
   - [Option 1: different query]
   - [Option 2: additional data needed]
   - [Option 3: related analysis available]

TONE: Helpful and honest. Never pretend to know what you don't."""


# ==================== VALIDATION RULES (COMPREHENSIVE) ====================

COMPREHENSIVE_VALIDATION_RULES = {
    'minimum_length': 50,
    'requires_numbers': True,
    'requires_context': True,
    'requires_limitations': True,
    'requires_structure': True,
    'max_length': 2000,  # Avoid overly verbose responses
    'must_answer_query': True,
    'must_acknowledge_uncertainty': True,
    'no_confabulation': True,
    'proper_punctuation': True,
}


def validate_for_production(response: str, query: str) -> dict:
    """Comprehensive production validation."""
    response_lower = response.lower()

    issues = []

    # Length checks
    if len(response) < 50:
        issues.append("Response too short - lacks detail")
    if len(response) > 2000:
        issues.append("Response too long - should be more concise")

    # Content checks
    if not any(c.isdigit() for c in response):
        issues.append("No specific numbers provided")

    # Context checks
    query_words = set(query.lower().split())
    response_words = set(response_lower.split())
    overlap = len(query_words & response_words) / len(query_words)
    if overlap < 0.3:
        issues.append("Response may not address original query")

    # Limitation checks
    limitation_words = {'however', 'note', 'limitation', 'caveat', 'missing', 'partial', 'caveat', 'uncertain', 'likely'}
    if not any(word in response_lower for word in limitation_words):
        issues.append("Doesn't mention limitations or caveats")

    # Structure checks
    has_structure = response.count('\n') > 2 or '-' in response or '•' in response
    if not has_structure:
        issues.append("Response lacks clear structure")

    # Uncertainty checks
    uncertainty_words = {'approximately', 'roughly', 'about', 'around', 'estimate', 'approximately', 'unclear'}
    has_uncertainty = any(word in response_lower for word in uncertainty_words)

    quality_score = max(0, 100 - (len(issues) * 15))

    return {
        'is_production_ready': len(issues) == 0 and quality_score >= 85,
        'quality_score': quality_score,
        'issues': issues,
        'requires_revision': len(issues) > 0,
        'revision_priority': 'high' if len(issues) > 3 else 'medium' if len(issues) > 0 else 'low',
    }
