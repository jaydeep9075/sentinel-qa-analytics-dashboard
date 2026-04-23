# test_tidb_ingestion.py
from ingester import UniversalIngester
import logging
import datetime

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    build_id = f"ingestion_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    print(f"Starting ingestion with build_id: {build_id}")

    ingester = UniversalIngester(data_base_path="../data")
    config_path = "../config.json"
    ingester.run_ingestion_from_config(config_path, build_id=build_id)