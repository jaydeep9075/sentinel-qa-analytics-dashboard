# test_allure_ingestion.py
from ingester import UniversalIngester
from datetime import datetime, timezone
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

if __name__ == "__main__":
    build_id = f"ingestion_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    print(f"Starting ingestion with build_id: {build_id}")
    ingester = UniversalIngester(data_base_path="../data")
    ingester.run_ingestion_from_config("../config2.json", build_id=build_id)
    print("Ingestion completed.")