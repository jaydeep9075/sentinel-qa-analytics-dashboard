import os
import json
import pandas as pd
import lancedb
import duckdb
from sqlalchemy import create_engine, text
import logging
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import quote_plus
from datetime import datetime

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TiDBIngester:
    def __init__(self, tidb_password: str, lancedb_path: str = "./data"):
        """
        Initialize TiDB ingester - Only fetches test_cases and test_results tables
        """
        # Setup paths
        self.lancedb_path = Path(lancedb_path).absolute()
        self.lancedb_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"LanceDB storage path: {self.lancedb_path}")
        
        # Encode password for URL
        encoded_password = quote_plus(tidb_password)
        
        # Connection string for TiDB
        self.connection_string = (
            f"mysql+pymysql://sC5aTifmN57gWAj.root:{encoded_password}"
            f"@gateway01.ap-northeast-1.prod.aws.tidbcloud.com:4000/dappled"
        )
        
        # Create database engine with SSL (disable verification for now)
        self.engine = create_engine(
            self.connection_string,
            connect_args={
                "ssl": {
                    "verify_cert": False,
                    "verify_identity": False
                }
            }
        )
        
        # Test connection
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1")).fetchone()
                logger.info("✅ Successfully connected to TiDB")
        except Exception as e:
            logger.error(f"❌ Failed to connect to TiDB: {e}")
            raise
        
        # Initialize LanceDB and DuckDB
        self.lance_db = lancedb.connect(str(self.lancedb_path))
        self.duck_db = duckdb.connect()
        
        # Create tables in LanceDB
        self._create_lance_tables()
    
    def _create_lance_tables(self):
        """Create LanceDB tables with proper schemas"""
        # Schema for test_cases table
        test_cases_schema = {
            "id": "int64",
            "project_id": "int64",
            "organization_id": "str",
            "case_code": "str",
            "case_key": "str",
            "module_name": "str",
            "test_suite": "str",
            "tags": "str",
            "title": "str",
            "description": "str",
            "precondition": "str",
            "steps": "str",
            "expected_result": "str",
            "type": "str",
            "priority": "str",
            "mode": "str",
            "created_by_id": "str",
            "shareable_link": "str",
            "created_at": "timestamp[ns]",
            "updated_at": "timestamp[ns]"
        }
        
        # Create test_cases table if it doesn't exist
        if "test_cases" not in self.lance_db.table_names():
            # Create empty DataFrame with proper columns
            empty_df = pd.DataFrame(columns=list(test_cases_schema.keys()))
            self.lance_db.create_table("test_cases", empty_df)
            logger.info("✅ Created test_cases table in LanceDB")
        
        # Schema for test_results table
        test_results_schema = {
            "id": "int64",
            "build_id": "int64",
            "project_id": "int64",
            "organization_id": "str",
            "spec_file": "str",
            "tests": "str",  # JSON stored as string
            "executed_at": "timestamp[ns]"
        }
        
        # Create test_results table if it doesn't exist
        if "test_results" not in self.lance_db.table_names():
            empty_df = pd.DataFrame(columns=list(test_results_schema.keys()))
            self.lance_db.create_table("test_results", empty_df)
            logger.info("✅ Created test_results table in LanceDB")
    
    def fetch_table_data(self, table_name: str) -> pd.DataFrame:
        """Fetch data from a specific TiDB table"""
        try:
            logger.info(f"Fetching data from {table_name}...")
            query = f"SELECT * FROM {table_name}"
            df = pd.read_sql(query, self.engine)
            logger.info(f"✅ Fetched {len(df)} rows from {table_name}")
            return df
        except Exception as e:
            logger.error(f"Error fetching {table_name}: {e}")
            return pd.DataFrame()
    
    def ingest_test_cases(self):
        """Ingest only test_cases table"""
        logger.info("\n" + "="*60)
        logger.info("📊 INGESTING TEST_CASES TABLE")
        logger.info("="*60)
        
        # Fetch data from TiDB
        df = self.fetch_table_data("test_cases")
        
        if df.empty:
            logger.warning("No data found in test_cases table")
            return 0
        
        # Data cleaning and transformation
        logger.info("Cleaning and transforming data...")
        
        # Convert datetime columns
        if 'created_at' in df.columns:
            df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')
        if 'updated_at' in df.columns:
            df['updated_at'] = pd.to_datetime(df['updated_at'], errors='coerce')
        
        # Handle JSON fields (tags)
        if 'tags' in df.columns:
            df['tags'] = df['tags'].apply(
                lambda x: json.dumps(x) if isinstance(x, (dict, list)) 
                else str(x) if pd.notna(x) else "{}"
            )
        
        # Convert all object columns to string and handle nulls
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].fillna("").astype(str)
        
        # Store in LanceDB
        try:
            table = self.lance_db.open_table("test_cases")
            records = df.to_dict('records')
            
            # Clear existing data if any (for fresh ingestion)
            if len(table.to_pandas()) > 0:
                logger.info("Clearing existing data from test_cases table...")
                # Create new table with fresh data
                self.lance_db.create_table("test_cases", records, mode="overwrite")
            else:
                table.add(records)
            
            logger.info(f"✅ Successfully ingested {len(df)} test cases to LanceDB")
            
            # Verify ingestion
            verify_df = self.lance_db.open_table("test_cases").to_pandas()
            logger.info(f"✅ Verification: {len(verify_df)} test cases now in LanceDB")
            
            return len(df)
            
        except Exception as e:
            logger.error(f"Error storing test_cases: {e}")
            # Fallback: overwrite the table
            self.lance_db.create_table("test_cases", df, mode="overwrite")
            logger.info(f"✅ Overwrote test_cases table with {len(df)} records")
            return len(df)
    
    def ingest_test_results(self):
        """Ingest only test_results table"""
        logger.info("\n" + "="*60)
        logger.info("📊 INGESTING TEST_RESULTS TABLE")
        logger.info("="*60)
        
        # Fetch data from TiDB
        df = self.fetch_table_data("test_results")
        
        if df.empty:
            logger.warning("No data found in test_results table")
            return 0
        
        # Data cleaning and transformation
        logger.info("Cleaning and transforming data...")
        
        # Convert datetime columns
        if 'executed_at' in df.columns:
            df['executed_at'] = pd.to_datetime(df['executed_at'], errors='coerce')
        
        # Handle JSON tests field
        if 'tests' in df.columns:
            df['tests'] = df['tests'].apply(
                lambda x: json.dumps(x) if isinstance(x, (dict, list)) 
                else str(x) if pd.notna(x) else "{}"
            )
        
        # Convert all object columns to string
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].fillna("").astype(str)
        
        # Store in LanceDB
        try:
            table = self.lance_db.open_table("test_results")
            records = df.to_dict('records')
            
            # Clear existing data if any
            if len(table.to_pandas()) > 0:
                logger.info("Clearing existing data from test_results table...")
                self.lance_db.create_table("test_results", records, mode="overwrite")
            else:
                table.add(records)
            
            logger.info(f"✅ Successfully ingested {len(df)} test results to LanceDB")
            
            # Verify ingestion
            verify_df = self.lance_db.open_table("test_results").to_pandas()
            logger.info(f"✅ Verification: {len(verify_df)} test results now in LanceDB")
            
            return len(df)
            
        except Exception as e:
            logger.error(f"Error storing test_results: {e}")
            self.lance_db.create_table("test_results", df, mode="overwrite")
            logger.info(f"✅ Overwrote test_results table with {len(df)} records")
            return len(df)
    
    def link_to_duckdb(self):
        """Link LanceDB tables to DuckDB for SQL queries"""
        logger.info("\n" + "="*60)
        logger.info("🔗 LINKING TO DUCKDB")
        logger.info("="*60)
        
        try:
            # Load test_cases into DuckDB
            test_cases_table = self.lance_db.open_table("test_cases")
            df_cases = test_cases_table.to_pandas()
            self.duck_db.register("test_cases", df_cases)
            logger.info(f"✅ Linked {len(df_cases)} test cases to DuckDB")
            
            # Load test_results into DuckDB
            test_results_table = self.lance_db.open_table("test_results")
            df_results = test_results_table.to_pandas()
            self.duck_db.register("test_results", df_results)
            logger.info(f"✅ Linked {len(df_results)} test results to DuckDB")
            
            return self.duck_db
            
        except Exception as e:
            logger.error(f"Error linking to DuckDB: {e}")
            return self.duck_db
    
    def run_full_ingestion(self):
        """Run complete ingestion for both tables"""
        logger.info("\n" + "="*60)
        logger.info("🚀 STARTING TIDB INGESTION PROCESS")
        logger.info("="*60)
        
        results = {}
        
        # Ingest test_cases
        results['test_cases'] = self.ingest_test_cases()
        
        # Ingest test_results
        results['test_results'] = self.ingest_test_results()
        
        # Link to DuckDB
        duckdb_conn = self.link_to_duckdb()
        
        # Print summary
        logger.info("\n" + "="*60)
        logger.info("📊 INGESTION SUMMARY")
        logger.info("="*60)
        logger.info(f"✅ test_cases ingested: {results['test_cases']} records")
        logger.info(f"✅ test_results ingested: {results['test_results']} records")
        logger.info(f"💾 Data stored in: {self.lancedb_path}")
        logger.info("="*60)
        
        return duckdb_conn

def main():
    """Main ingestion function"""
    # Get password from environment
    password = os.getenv("TIDB_PASSWORD", "")
    
    if not password:
        logger.error("❌ TIDB_PASSWORD not found in .env file")
        logger.info("Please create a .env file with: TIDB_PASSWORD=your_password_here")
        return
    
    try:
        # Initialize ingester
        ingester = TiDBIngester(
            tidb_password=password,
            lancedb_path="./data"
        )
        
        # Run ingestion
        duckdb_conn = ingester.run_full_ingestion()
        
        # Test queries to verify data is accessible
        logger.info("\n" + "="*60)
        logger.info("🔍 VERIFYING DATA ACCESS")
        logger.info("="*60)
        
        # Test test_cases query
        try:
            result = duckdb_conn.execute("""
                SELECT 
                    COUNT(*) as total_cases,
                    COUNT(DISTINCT project_id) as projects,
                    COUNT(DISTINCT module_name) as modules,
                    COUNT(DISTINCT priority) as priorities
                FROM test_cases
            """).fetchall()
            
            logger.info(f"✅ test_cases summary:")
            logger.info(f"   - Total cases: {result[0][0]}")
            logger.info(f"   - Projects: {result[0][1]}")
            logger.info(f"   - Modules: {result[0][2]}")
            logger.info(f"   - Priorities: {result[0][3]}")
            
        except Exception as e:
            logger.warning(f"Could not query test_cases: {e}")
        
        # Test test_results query
        try:
            result = duckdb_conn.execute("""
                SELECT 
                    COUNT(*) as total_results,
                    COUNT(DISTINCT build_id) as builds,
                    MIN(executed_at) as earliest,
                    MAX(executed_at) as latest
                FROM test_results
            """).fetchall()
            
            logger.info(f"✅ test_results summary:")
            logger.info(f"   - Total results: {result[0][0]}")
            logger.info(f"   - Builds: {result[0][1]}")
            if result[0][2]:
                logger.info(f"   - Date range: {result[0][2]} to {result[0][3]}")
            
        except Exception as e:
            logger.warning(f"Could not query test_results: {e}")
        
        logger.info("\n" + "="*60)
        logger.info("🎉 INGESTION COMPLETE! You can now start the services.")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"❌ Ingestion failed: {e}")
        raise

if __name__ == "__main__":
    main()