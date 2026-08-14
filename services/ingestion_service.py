"""
Production-grade ingestion service with connector field mapping and validation.
"""

import json
import logging
import os
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)


class ConnectorFieldMapper:
    """Maps connector types to required/optional fields."""

    CONNECTOR_CONFIGS = {
        'allure': {
            'name': 'Allure Test Results',
            'description': 'Ingest test results from Allure artifacts',
            'fields': [
                {
                    'name': 'path',
                    'type': 'text',
                    'label': 'Path to Allure Results',
                    'placeholder': '/path/to/allure-results or /path/to/allure.html',
                    'required': True,
                    'help': 'Local folder with Allure JSON results, a .zip archive, or an HTML report file',
                    'validation': 'path_exists'
                }
            ],
            'auto_detect': True,
            'formats': ['JSON results files (*-result.json)', 'Zip archives (.zip)', 'HTML reports (index.html)']
        },

        'csv': {
            'name': 'CSV Files',
            'description': 'Ingest tabular data from CSV files',
            'fields': [
                {
                    'name': 'path',
                    'type': 'text',
                    'label': 'Path to CSV File',
                    'placeholder': '/path/to/data.csv',
                    'required': True,
                    'help': 'CSV file to ingest',
                    'validation': 'path_exists'
                },
                {
                    'name': 'delimiter',
                    'type': 'select',
                    'label': 'Delimiter',
                    'options': [
                        {'value': ',', 'label': 'Comma (,) - default'},
                        {'value': ';', 'label': 'Semicolon (;)'},
                        {'value': '\t', 'label': 'Tab'},
                        {'value': '|', 'label': 'Pipe (|)'},
                        {'value': 'auto', 'label': 'Auto-detect'}
                    ],
                    'required': False,
                    'default': 'auto',
                    'help': 'Column delimiter in CSV'
                },
                {
                    'name': 'has_header',
                    'type': 'checkbox',
                    'label': 'Has header row',
                    'required': False,
                    'default': True,
                    'help': 'First row contains column names'
                },
                {
                    'name': 'encoding',
                    'type': 'select',
                    'label': 'Encoding',
                    'options': [
                        {'value': 'utf-8', 'label': 'UTF-8 (default)'},
                        {'value': 'latin-1', 'label': 'Latin-1'},
                        {'value': 'cp1252', 'label': 'Windows-1252'},
                        {'value': 'auto', 'label': 'Auto-detect'}
                    ],
                    'required': False,
                    'default': 'auto'
                }
            ],
            'auto_detect': True,
            'formats': ['CSV files (.csv)', 'TSV files (.tsv)']
        },

        'excel': {
            'name': 'Excel Files',
            'description': 'Ingest tabular data from Excel workbooks',
            'fields': [
                {
                    'name': 'path',
                    'type': 'text',
                    'label': 'Path to Excel File',
                    'placeholder': '/path/to/data.xlsx',
                    'required': True,
                    'help': 'Excel workbook to ingest',
                    'validation': 'path_exists'
                },
                {
                    'name': 'sheet_name',
                    'type': 'text',
                    'label': 'Sheet name (optional)',
                    'placeholder': 'Sheet1',
                    'required': False,
                    'help': 'Ingest only this sheet; leave empty to ingest every sheet as its own table'
                }
            ],
            'auto_detect': True,
            'formats': ['Excel workbooks (.xlsx, .xls)']
        },

        'database': {
            'name': 'Database',
            'description': 'Ingest data from SQL databases',
            'fields': [
                {
                    'name': 'connection_string',
                    'type': 'text',
                    'label': 'Connection String',
                    'placeholder': 'postgresql://user:pass@host:5432/dbname',
                    'required': True,
                    'help': 'Database connection string (SQLAlchemy format)',
                    'validation': 'connection_string'
                },
                {
                    'name': 'tables',
                    'type': 'text',
                    'label': 'Tables to ingest (comma-separated)',
                    'placeholder': 'table1,table2,table3 or leave empty for all',
                    'required': False,
                    'help': 'Specific tables to ingest'
                },
                {
                    'name': 'batch_size',
                    'type': 'number',
                    'label': 'Batch size',
                    'placeholder': '50000',
                    'required': False,
                    'default': 50000,
                    'help': 'Rows fetched per streamed chunk'
                }
            ],
            'auto_detect': False,
            'formats': ['PostgreSQL', 'MySQL', 'SQLite']
        },

        'api': {
            'name': 'REST API',
            'description': 'Ingest data from REST APIs',
            'fields': [
                {
                    'name': 'url',
                    'type': 'text',
                    'label': 'API URL',
                    'placeholder': 'https://api.example.com/data',
                    'required': True,
                    'help': 'REST API endpoint URL',
                    'validation': 'url'
                },
                {
                    'name': 'method',
                    'type': 'select',
                    'label': 'HTTP Method',
                    'options': [
                        {'value': 'GET', 'label': 'GET'},
                        {'value': 'POST', 'label': 'POST'}
                    ],
                    'required': False,
                    'default': 'GET'
                },
                {
                    'name': 'headers',
                    'type': 'textarea',
                    'label': 'Headers (JSON)',
                    'placeholder': '{"Authorization": "Bearer token"}',
                    'required': False,
                    'help': 'HTTP headers as JSON'
                },
                {
                    'name': 'body',
                    'type': 'textarea',
                    'label': 'Request body (JSON)',
                    'placeholder': '{"query": "..."}',
                    'required': False,
                    'help': 'Only sent when the method is POST'
                }
            ],
            'auto_detect': False,
            'formats': ['REST APIs returning JSON']
        }
    }

    @classmethod
    def get_connector_config(cls, connector_type: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a connector type."""
        return cls.CONNECTOR_CONFIGS.get(connector_type.lower())

    @classmethod
    def get_all_connectors(cls) -> Dict[str, Dict[str, Any]]:
        """Get all available connectors."""
        return cls.CONNECTOR_CONFIGS

    @classmethod
    def auto_detect_type(cls, path: str) -> str:
        """Auto-detect connector type from path/file."""
        path_lower = str(path).lower()

        if 'allure' in path_lower or path_lower.endswith('.zip'):
            return 'allure'

        ext = Path(path).suffix.lower() if path else ''

        type_map = {
            '.csv': 'csv',
            '.tsv': 'csv',
            '.xlsx': 'excel',
            '.xls': 'excel',
        }

        return type_map.get(ext, 'allure')  # Default to allure for directories


class IngestionValidator:
    """Validate ingestion configurations."""

    @staticmethod
    def validate_allure_config(config: Dict[str, Any]) -> tuple[bool, str]:
        """Validate Allure connector config."""
        path = config.get('path', '')

        if not path:
            return False, "Path is required"

        if not Path(path).exists():
            return False, f"Path does not exist: {path}"

        # Check if it's an Allure directory, a zip archive, or an HTML report
        is_html = str(path).lower().endswith(('.html', '.htm'))
        is_zip = str(path).lower().endswith('.zip')
        is_dir = Path(path).is_dir()

        if not (is_html or is_zip or is_dir):
            return False, "Path must be a directory, a .zip archive, or an HTML file"

        return True, "Valid Allure configuration"

    @staticmethod
    def validate_csv_config(config: Dict[str, Any]) -> tuple[bool, str]:
        """Validate CSV connector config."""
        path = config.get('path', '')

        if not path:
            return False, "Path is required"

        if not Path(path).exists():
            return False, f"Path does not exist: {path}"

        if not str(path).lower().endswith(('.csv', '.tsv')):
            return False, "File must be CSV or TSV"

        return True, "Valid CSV configuration"

    @staticmethod
    def validate_excel_config(config: Dict[str, Any]) -> tuple[bool, str]:
        """Validate Excel connector config."""
        path = config.get('path', '')

        if not path:
            return False, "Path is required"

        if not Path(path).exists():
            return False, f"Path does not exist: {path}"

        if not str(path).lower().endswith(('.xlsx', '.xls')):
            return False, "File must be .xlsx or .xls"

        return True, "Valid Excel configuration"

    @staticmethod
    def validate_database_config(config: Dict[str, Any]) -> tuple[bool, str]:
        """Validate database connector config."""
        conn_str = config.get('connection_string', '')

        if not conn_str:
            return False, "Connection string is required"

        # Basic validation
        if not any(x in conn_str for x in ['postgresql', 'mysql', 'sqlite', 'mssql']):
            return False, "Invalid database connection string"

        return True, "Valid database configuration"

    @staticmethod
    def validate_api_config(config: Dict[str, Any]) -> tuple[bool, str]:
        """Validate API connector config."""
        url = config.get('url', '')

        if not url:
            return False, "URL is required"

        if not url.startswith(('http://', 'https://')):
            return False, "URL must start with http:// or https://"

        return True, "Valid API configuration"

    @classmethod
    def validate(cls, connector_type: str, config: Dict[str, Any]) -> tuple[bool, str]:
        """Validate connector configuration."""
        validators = {
            'allure': cls.validate_allure_config,
            'csv': cls.validate_csv_config,
            'excel': cls.validate_excel_config,
            'database': cls.validate_database_config,
            'api': cls.validate_api_config,
        }

        validator = validators.get(connector_type.lower())
        if not validator:
            return False, f"Unknown connector type: {connector_type}"

        return validator(config)


class IngestionService:
    """Main ingestion service."""

    def __init__(self):
        self.field_mapper = ConnectorFieldMapper()
        self.validator = IngestionValidator()

    def get_connector_options(self) -> Dict[str, Any]:
        """Get all connector options for UI."""
        connectors = self.field_mapper.get_all_connectors()

        return {
            'connectors': [
                {
                    'id': conn_id,
                    'name': conf['name'],
                    'description': conf['description'],
                    'fields': conf['fields'],
                    'formats': conf['formats'],
                    'auto_detect': conf['auto_detect'],
                }
                for conn_id, conf in connectors.items()
            ],
            'auto_detect_supported': True,
        }

    def prepare_ingestion(self, connector_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare ingestion by validating config."""
        is_valid, message = self.validator.validate(connector_type, config)

        if not is_valid:
            return {
                'success': False,
                'error': message,
                'connector_type': connector_type,
            }

        return {
            'success': True,
            'message': message,
            'connector_type': connector_type,
            'config': config,
        }

    def suggest_fields(self, path: str) -> Dict[str, Any]:
        """Suggest field values based on path."""
        connector_type = self.field_mapper.auto_detect_type(path)

        config = self.field_mapper.get_connector_config(connector_type)

        return {
            'detected_type': connector_type,
            'connector_name': config['name'] if config else 'Unknown',
            'suggested_fields': config['fields'] if config else [],
            'formats': config['formats'] if config else [],
        }
