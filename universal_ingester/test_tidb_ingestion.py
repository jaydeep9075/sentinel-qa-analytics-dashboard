# test_tidb_ingestion.py
from ingester import UniversalIngester
import logging
import datetime

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    # Generate a unique build_id for this ingestion run
    build_id = f"build_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    print(f"Starting ingestion with build_id: {build_id}")

    ingester = UniversalIngester(lancedb_path="./lancedb_tidb_test")
    config_path = "../config.json"
    ingester.run_ingestion_from_config(config_path, build_id=build_id)
    
    print("\n=== LanceDB tables ===")
    print(ingester.lance_db.table_names())
    
    for table in ingester.lance_db.table_names():
        if table.startswith("structured_"):
            df = ingester.lance_db.open_table(table).to_pandas()
            print(f"\n{table}: {len(df)} rows")
            if len(df) > 0:
                print(df.head(2))
    
    docs_table = ingester.lance_db.open_table("documents")
    docs_df = docs_table.to_pandas()
    print(f"\nDocuments table: {len(docs_df)} rows")
    if len(docs_df) > 0:
        print("Sample document:")
        print(docs_df.iloc[0]['text'][:200])
    
    from utils import EmbeddingGenerator
    embedder = EmbeddingGenerator()
    query = "What is the priority of test cases?"
    query_emb = embedder.embed([query])[0]
    
    results = docs_table.search(query_emb).limit(3).to_list()
    print("\n=== Search results ===")
    for r in results:
        print(r['text'][:300])
        print("---")