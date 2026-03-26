import lancedb
import pandas as pd

# 1. Connect to the same folder used by the ingestor
db = lancedb.connect("./sentinel_data")

# 🚨 CHANGE THIS LINE: Match the name from your successful logs
table_name = "local_test_results" 

# Note: Use list_tables() as table_names() is being deprecated
if table_name in db.list_tables():
    tbl = db.open_table(table_name)
    df = tbl.to_pandas()
    
    print(f"\n--- [ INSIDE DATA: {table_name} ] ---")
    
    # This helps see the 'rag_context' we built for the LLM
    pd.set_option('display.max_columns', None) 
    pd.set_option('display.width', 1000)
    
    print(df.head(20)) 
else:
    # This will print what is actually available if it fails again
    print(f"❌ Table '{table_name}' not found.")
    print(f"📂 Available tables are: {db.list_tables()}")