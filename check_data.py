# reset_chart_table.py
import lancedb
db = lancedb.connect("./universal_ingester/lancedb_tidb_test")
if "chart_history" in db.list_tables():
    db.drop_table("chart_history")
    print("Dropped chart_history table")
else:
    print("Table not found")