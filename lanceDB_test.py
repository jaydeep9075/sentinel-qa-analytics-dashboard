# diagnostics.py
import lancedb
import pandas as pd

def check_lance_data():
    """Check what data is actually stored in LanceDB"""
    
    # Connect to the database
    db = lancedb.connect("./sentinel_data")
    
    # Get all tables
    result = db.list_tables()
    
    # Handle tuple return
    if isinstance(result, tuple):
        tables = result[0]
        page_token = result[1]
    else:
        tables = result
        page_token = None
    
    print(f"📂 Available tables: {tables}")
    print(f"Page token: {page_token}\n")
    
    # Check each table
    for table_name in tables:
        print(f"\n{'='*60}")
        print(f"Table: {table_name}")
        print(f"{'='*60}")
        
        try:
            # Open the table
            table = db.open_table(table_name)
            
            # Check row count
            row_count = table.count_rows()
            print(f"Row count: {row_count}")
            
            if row_count > 0:
                # Get first few rows
                df = table.to_pandas()
                print(f"Columns: {list(df.columns)}")
                print(f"\nFirst 2 rows:")
                print(df.head(2).to_string())
                
                # Check if data is actually there
                print(f"\nData sample:")
                for col in df.columns[:5]:  # Show first 5 columns
                    if len(df) > 0:
                        print(f"  {col}: {df[col].iloc[0][:100] if isinstance(df[col].iloc[0], str) else df[col].iloc[0]}")
            else:
                print("⚠️ Table is empty (0 rows)")
                
        except Exception as e:
            print(f"❌ Error reading table: {e}")
            import traceback
            traceback.print_exc()

def check_file_system():
    """Check what files exist in the sentinel_data directory"""
    import os
    
    print("\n" + "="*60)
    print("Files in ./sentinel_data directory:")
    print("="*60)
    
    if os.path.exists("./sentinel_data"):
        for root, dirs, files in os.walk("./sentinel_data"):
            level = root.replace("./sentinel_data", "").count(os.sep)
            indent = " " * 2 * level
            print(f"{indent}{os.path.basename(root)}/")
            subindent = " " * 2 * (level + 1)
            for file in files:
                file_path = os.path.join(root, file)
                file_size = os.path.getsize(file_path)
                print(f"{subindent}{file} ({file_size} bytes)")
    else:
        print("❌ ./sentinel_data directory not found")

if __name__ == "__main__":
    print("🔍 LanceDB Data Diagnostics\n")
    check_lance_data()
    check_file_system()