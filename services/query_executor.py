"""
Query executor - converts AI analysis to database queries and executes them.
Handles both LanceDB (vector search) and DuckDB (SQL execution).
"""

import json
import logging
from typing import Optional, Dict, Any, List
import duckdb

logger = logging.getLogger(__name__)


class QueryBuilder:
    """Build SQL queries from prompt analysis."""

    def __init__(self, schema_info: Optional[Dict[str, Any]] = None):
        self.schema_info = schema_info or {}
        self.fields = self.schema_info.get('fields', {})

    def build_query(self, analysis: Dict[str, Any], table_name: str = "test_results") -> str:
        """
        Build SQL query from prompt analysis.

        Args:
            analysis: Result from PromptAnalyzer
            table_name: Table to query

        Returns:
            SQL query string
        """

        intent = analysis.get('intent', 'summary')
        filters = analysis.get('filters', {})
        aggregations = analysis.get('aggregations', [])
        sort = analysis.get('sort', {})

        # Build WHERE clause
        where_clause = self._build_where_clause(filters)

        # Build SELECT clause based on intent
        select_clause = self._build_select_clause(intent, aggregations)

        # Build GROUP BY if needed
        group_by_clause = self._build_group_by(intent, analysis)

        # Build ORDER BY
        order_by_clause = self._build_order_by(sort, intent)

        # Combine
        query = f"SELECT {select_clause} FROM {table_name}"

        if where_clause:
            query += f" WHERE {where_clause}"

        if group_by_clause:
            query += f" GROUP BY {group_by_clause}"

        if order_by_clause:
            query += f" ORDER BY {order_by_clause}"

        # Limit results for some queries
        if intent in ('top', 'distribution'):
            query += " LIMIT 20"

        logger.info(f"Built query: {query}")
        return query

    def _build_where_clause(self, filters: Dict[str, Any]) -> str:
        """Build WHERE clause from filters."""
        conditions = []

        for field, value in filters.items():
            if field == 'status':
                # Status filter
                if isinstance(value, str):
                    conditions.append(f"status = '{value}'")
                elif isinstance(value, list):
                    statuses = "', '".join(value)
                    conditions.append(f"status IN ('{statuses}')")

            elif field == 'module':
                # Module filter
                conditions.append(f"module_name = '{value}'")

            elif field == 'project':
                # Project filter
                conditions.append(f"project_name = '{value}'")

            elif field == 'platform':
                # Platform filter
                conditions.append(f"platform_type = '{value}'")

            elif field == 'date_range':
                # Date range filter
                if isinstance(value, dict):
                    start = value.get('start')
                    end = value.get('end')
                    if start:
                        conditions.append(f"executed_at >= '{start}'")
                    if end:
                        conditions.append(f"executed_at <= '{end}'")

        return " AND ".join(conditions)

    def _build_select_clause(self, intent: str, aggregations: List[str]) -> str:
        """Build SELECT clause based on intent."""

        if intent == 'count':
            return "COUNT(*) as total_count"

        if intent == 'top':
            return "test_name, COUNT(*) as count"

        if intent == 'distribution':
            return "status, COUNT(*) as count"

        if intent == 'trend':
            return "DATE(executed_at) as date, COUNT(*) as count"

        if intent == 'comparison':
            return "module_name, status, COUNT(*) as count, AVG(duration_seconds) as avg_duration"

        # Summary or detail
        if 'avg' in aggregations or 'sum' in aggregations:
            return "test_name, status, duration_seconds, module_name"

        return "*"

    def _build_group_by(self, intent: str, analysis: Dict[str, Any]) -> str:
        """Build GROUP BY clause if needed."""

        if intent == 'top':
            return "test_name"

        if intent == 'distribution':
            return "status"

        if intent == 'trend':
            return "DATE(executed_at)"

        if intent == 'comparison':
            return "module_name, status"

        return ""

    def _build_order_by(self, sort: Optional[Dict[str, Any]], intent: str) -> str:
        """Build ORDER BY clause."""

        if sort:
            field = sort.get('field', 'count')
            direction = sort.get('direction', 'desc').upper()
            return f"{field} {direction}"

        # Default sort based on intent
        if intent == 'top':
            return "count DESC"

        if intent == 'trend':
            return "date ASC"

        return ""


class QueryExecutor:
    """Execute queries against DuckDB."""

    def __init__(self, duckdb_connection=None):
        self.db = duckdb_connection or duckdb.connect()
        self.query_builder = QueryBuilder()

    def execute(self, analysis: Dict[str, Any], table_name: str = "test_results") -> Dict[str, Any]:
        """
        Execute query and return results with metadata.

        Returns:
        {
            'success': bool,
            'query': str,
            'results': [...],
            'result_count': int,
            'execution_time_ms': float,
            'error': str (if failed)
        }
        """

        import time

        try:
            # Build query
            query = self.query_builder.build_query(analysis, table_name)

            # Execute
            start_time = time.time()
            result = self.db.execute(query).fetch_all()
            execution_time = (time.time() - start_time) * 1000

            # Get column names
            columns = [desc[0] for desc in self.db.description or []]

            # Convert to list of dicts
            results = [
                dict(zip(columns, row))
                for row in result
            ]

            logger.info(f"Query executed: {len(results)} rows in {execution_time:.1f}ms")

            return {
                'success': True,
                'query': query,
                'results': results,
                'result_count': len(results),
                'execution_time_ms': round(execution_time, 2),
                'columns': columns,
            }

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return {
                'success': False,
                'query': query if 'query' in locals() else '',
                'results': [],
                'result_count': 0,
                'execution_time_ms': 0,
                'error': str(e),
            }

    def register_table(self, table_name: str, data):
        """Register a table in DuckDB."""
        try:
            self.db.register(table_name, data)
            logger.info(f"Registered table: {table_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to register table {table_name}: {e}")
            return False

    def get_schema(self, table_name: str) -> Dict[str, str]:
        """Get table schema."""
        try:
            result = self.db.execute(f"DESCRIBE {table_name}").fetch_all()
            schema = {row[0]: row[1] for row in result}
            return schema
        except Exception as e:
            logger.warning(f"Failed to get schema for {table_name}: {e}")
            return {}


class LanceDBSearcher:
    """Search LanceDB for relevant documents/chunks."""

    def __init__(self, lancedb_connection=None):
        self.lancedb = lancedb_connection

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search LanceDB for similar vectors.

        Args:
            query_embedding: Vector embedding of query
            top_k: Number of results to return
            filters: Optional metadata filters

        Returns:
            List of matching documents with embeddings + metadata
        """

        if not self.lancedb:
            return []

        try:
            # Search documents table
            results = (
                self.lancedb
                .open_table("documents")
                .search(query_embedding)
                .limit(top_k)
                .to_list()
            )

            logger.info(f"LanceDB search returned {len(results)} results")
            return results

        except Exception as e:
            logger.warning(f"LanceDB search failed: {e}")
            return []

    def get_context_from_results(
        self,
        search_results: List[Dict[str, Any]]
    ) -> str:
        """Format search results as context for LLM."""

        if not search_results:
            return ""

        context_lines = ["Retrieved relevant data:", ""]

        for i, result in enumerate(search_results[:5], 1):
            text = result.get('text', str(result))
            metadata = result.get('metadata', {})

            # Parse metadata if JSON
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except:
                    pass

            context_lines.append(f"{i}. {text[:200]}")
            if metadata:
                context_lines.append(f"   (metadata: {json.dumps(metadata, default=str)[:100]})")

        return "\n".join(context_lines)


class ResponseFormatter:
    """Format query results into natural language response."""

    @staticmethod
    def format_response(
        intent: str,
        results: List[Dict[str, Any]],
        analysis: Dict[str, Any]
    ) -> str:
        """Format database results into natural language."""

        if not results:
            return "No data found matching your query. Please try refining your search."

        if intent == 'count':
            row = results[0]
            count = row.get('total_count', 0)
            return f"Total: {count} items found."

        if intent == 'top':
            lines = [f"Top items by count:"]
            for i, row in enumerate(results[:10], 1):
                name = row.get('test_name', row.get('name', 'Unknown'))
                count = row.get('count', 0)
                lines.append(f"{i}. {name}: {count}")
            return "\n".join(lines)

        if intent == 'distribution':
            lines = [f"Distribution:"]
            total = sum(r.get('count', 0) for r in results)
            for row in results:
                status = row.get('status', 'Unknown')
                count = row.get('count', 0)
                percentage = (count / total * 100) if total else 0
                lines.append(f"- {status}: {count} ({percentage:.1f}%)")
            return "\n".join(lines)

        if intent == 'trend':
            lines = [f"Trend over time:"]
            for row in results:
                date = row.get('date', 'Unknown')
                count = row.get('count', 0)
                lines.append(f"- {date}: {count}")
            return "\n".join(lines)

        if intent == 'comparison':
            lines = [f"Comparison:"]
            for row in results:
                module = row.get('module_name', 'Unknown')
                status = row.get('status', 'Unknown')
                count = row.get('count', 0)
                lines.append(f"- {module} ({status}): {count}")
            return "\n".join(lines)

        # Default: summary of results
        lines = [f"Found {len(results)} results:"]
        for i, row in enumerate(results[:5], 1):
            lines.append(f"{i}. {json.dumps(row, default=str)[:100]}")
        return "\n".join(lines)
