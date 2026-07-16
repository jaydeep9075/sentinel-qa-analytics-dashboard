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
                    'help': 'Local folder with Allure JSON results or HTML report file',
                    'validation': 'path_exists'
                },
                {
                    'name': 'parse_html',
                    'type': 'checkbox',
                    'label': 'Also parse HTML artifacts',
                    'required': False,
                    'default': True,
                    'help': 'Extract data from Allure HTML reports if JSON not found'
                },
                {
                    'name': 'project_name',
                    'type': 'text',
                    'label': 'Project Name (optional)',
                    'placeholder': 'e.g., WebApp, MobileApp',
                    'required': False,
                    'help': 'Override or tag all tests with this project name'
                }
            ],
            'auto_detect': True,
            'formats': ['JSON results files (*-result.json)', 'HTML reports (index.html)']
        },

        'json': {
            'name': 'JSON Files',
            'description': 'Ingest nested or flat JSON data',
            'fields': [
                {
                    'name': 'path',
                    'type': 'text',
                    'label': 'Path to JSON File or Folder',
                    'placeholder': '/path/to/data.json or /path/to/folder',
                    'required': True,
                    'help': 'Single JSON file or folder containing JSON files',
                    'validation': 'path_exists'
                },
                {
                    'name': 'nested_handling',
                    'type': 'select',
                    'label': 'Handle Nested Objects',
                    'options': [
                        {'value': 'flatten', 'label': 'Flatten with dot notation (default)'},
                        {'value': 'keep_nested', 'label': 'Keep nested structure'},
                        {'value': 'auto', 'label': 'Auto-detect best approach'}
                    ],
                    'required': False,
                    'default': 'flatten',
                    'help': 'How to handle nested JSON objects'
                },
                {
                    'name': 'array_handling',
                    'type': 'select',
                    'label': 'Handle JSON Arrays',
                    'options': [
                        {'value': 'expand', 'label': 'Expand as rows (default)'},
                        {'value': 'stringify', 'label': 'Convert to JSON strings'}
                    ],
                    'required': False,
                    'default': 'expand',
                    'help': 'How to handle arrays in JSON'
                },
                {
                    'name': 'auto_schema',
                    'type': 'checkbox',
                    'label': 'Auto-detect schema',
                    'required': False,
                    'default': True,
                    'help': 'Automatically detect field types and purposes'
                }
            ],
            'auto_detect': True,
            'formats': ['JSON files (.json)', 'JSONL files (.jsonl)', 'JSON folders']
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
                    'placeholder': '1000',
                    'required': False,
                    'default': 1000,
                    'help': 'Number of rows per batch'
                }
            ],
            'auto_detect': False,
            'formats': ['PostgreSQL', 'MySQL', 'SQL Server', 'SQLite']
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
                    'name': 'pagination',
                    'type': 'select',
                    'label': 'Pagination',
                    'options': [
                        {'value': 'none', 'label': 'No pagination'},
                        {'value': 'offset', 'label': 'Offset-based'},
                        {'value': 'cursor', 'label': 'Cursor-based'}
                    ],
                    'required': False,
                    'default': 'none'
                }
            ],
            'auto_detect': False,
            'formats': ['REST APIs', 'JSON APIs', 'GraphQL']
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

        if 'allure' in path_lower:
            return 'allure'

        ext = Path(path).suffix.lower() if path else ''

        type_map = {
            '.json': 'json',
            '.jsonl': 'json',
            '.csv': 'csv',
            '.tsv': 'csv',
            '.xlsx': 'csv',  # Treat as tabular
            '.xls': 'csv',
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

        # Check if it's Allure directory or HTML file
        is_html = str(path).endswith(('.html', '.htm'))
        is_dir = Path(path).is_dir()

        if not (is_html or is_dir):
            return False, "Path must be a directory or HTML file"

        return True, "Valid Allure configuration"

    @staticmethod
    def validate_json_config(config: Dict[str, Any]) -> tuple[bool, str]:
        """Validate JSON connector config."""
        path = config.get('path', '')

        if not path:
            return False, "Path is required"

        if not Path(path).exists():
            return False, f"Path does not exist: {path}"

        return True, "Valid JSON configuration"

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
            'json': cls.validate_json_config,
            'csv': cls.validate_csv_config,
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
