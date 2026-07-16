# 🔧 Troubleshooting Guide - Dashboard Issues

## Issue 1: "Table with name flattened_tests does not exist"

### What's Happening
Dashboard tries to query `flattened_tests` table that doesn't exist.

### Root Cause
Ingestion hasn't completed successfully, so LanceDB tables were never created.

### Solution

**Step 1: Check Ingestion Status**
```bash
# Look for recent ingestion errors in server logs
# Search for "ERROR" or "Ingestion ... failed"
```

**Step 2: Verify Allure Path**
```bash
# Make sure path is correct and accessible
# Valid paths:
# - C:\Users\admin\Downloads\allure-results
# - C:\path\to\allure-results
# NOT:
# - C:\Users\admin\Downloads\allure-results 1 (1)\allure-results  ❌ (spaces/parens)
```

**Step 3: Re-run Ingestion**
1. Open dashboard UI
2. Click "New Ingestion"
3. Enter correct path to Allure results
4. Wait for completion

**Step 4: Verify Tables Exist**
```bash
# After successful ingestion, these tables should exist:
# - flattened_tests
# - module_metrics  
# - project_metrics
# - test_cases
```

If issue persists, see **Issue 2** below.

---

## Issue 2: "Path does not exist: C:\Users\admin\Downloads\allure-results 1 (1)\allure-results"

### What's Happening
Ingestion fails immediately because path validation fails.

### Root Cause
Windows paths with spaces or special characters like `(1)` aren't being handled correctly.

### Solution - ALREADY FIXED ✅

The path handling has been improved in `allure_connector.py` to:
1. Strip quotes properly
2. Normalize backslashes
3. Try parent directories
4. Give better error messages

**Workaround if Still Failing**:

**Option A: Use a path without spaces**
```bash
# Copy allure data to path without spaces
mkdir C:\data\allure
# Copy your allure-results to C:\data\allure
# Then ingest from C:\data\allure
```

**Option B: Use shorter UNC path**
```bash
# Instead of: C:\Users\admin\Downloads\allure-results 1 (1)\allure-results
# Use: C:\Users\admin\Downloads\allure-results
```

**Option C: Check exact path**
```bash
# Open cmd and type:
dir C:\Users\admin\Downloads\
# See what folders actually exist
# Use the exact name shown
```

---

## Complete Fix Checklist

### ✅ For Both Issues

**1. Update Code (Already Done)**
```bash
# The allure_connector.py has been updated with better path handling
# No action needed - just restart server
```

**2. Restart Server**
```bash
# Stop the server (Ctrl+C)
# Clear any cached data (optional):
#   - Delete `data/ingestions/` folder if needed
# Restart:
python -m services.main
```

**3. Verify System**
```bash
# Run verification script
python verify_system.py
# Answer questions when prompted
# Should see ✅ for all checks
```

**4. Test Ingestion**
```
1. Open dashboard: http://localhost:8000/frontend/index.html
2. Click "Ingest Data"
3. Select Connector: "Allure"
4. Enter path: C:\path\to\your\allure-results
5. Click "Start Ingestion"
6. Wait for completion
7. Check dashboard for data
```

---

## Common Paths to Try

### Windows
```bash
C:\Users\{YourName}\Downloads\allure-results
C:\data\allure-results
C:\Users\{YourName}\Desktop\allure-results
```

### Finding Your Allure Data
```bash
# Search for allure-result.json files
cd C:\
for /r . %f in (*-result.json) do @echo %f
```

---

## Debugging Steps

### 1. Check Server Logs

Look for these patterns:

**✅ Good - Ingestion succeeded:**
```
INFO:services.ingestion_jobs:Ingestion ingestion_20260716_113530 completed
INFO:services.data_loader:Registered flattened_tests: 608 rows
```

**❌ Bad - Ingestion failed:**
```
ERROR:services.ingestion_jobs:Ingestion ingestion_20260716_113530 failed
ERROR:Path does not exist: C:\...
```

### 2. Check LanceDB Tables

After successful ingestion, tables should be created:
```
INFO:services.data_loader:LanceDB tables for 'ingestion_20260716_113530': 
['structured_test_results', 'structured_test_module_metrics', ...]
```

If you see `[]` (empty list), ingestion didn't create tables.

### 3. Check Dashboard Queries

The dashboard tries to query `flattened_tests`. If it doesn't exist:
```
ERROR:__main__:Error computing overview status: Catalog Error: 
Table with name flattened_tests does not exist!
```

This means `init_data()` didn't run successfully.

---

## Full Recovery Steps

If everything is broken, do this:

**1. Stop Server**
```bash
Ctrl+C
```

**2. Clear Old Data**
```bash
# Delete ingestion cache (optional, keeps existing data)
# rm -r data/ingestions/

# Or start fresh (deletes all ingested data)
# rm -r data/
```

**3. Restart Server**
```bash
python -m services.main
```

**4. Re-ingest Data**
```
- Open http://localhost:8000/frontend/index.html
- Click "New Ingestion"
- Select "Allure Results"
- Enter path: C:\Users\admin\Downloads\allure-results
- Click "Start"
- Wait for completion
```

**5. Verify Dashboard**
```
- Should show pass rate %
- Should show module stats
- Should show no errors in server logs
```

---

## Performance Issues

### Dashboard Still Slow?

**Cause**: No indexes created on DuckDB tables

**Fix**:
```bash
# After successful ingestion, create indexes
python -c "
import duckdb
conn = duckdb.connect('./data/ingestions/ingestion_XXXXX/duckdb.db')
conn.execute('CREATE INDEX IF NOT EXISTS idx_status ON flattened_tests(status)')
conn.execute('CREATE INDEX IF NOT EXISTS idx_module ON flattened_tests(module_name)')
"
```

### API Response Slow?

**Cause**: Large result sets not paginated

**Fix**: Ensure you're getting paginated results:
```bash
# Good (paginated):
curl "http://localhost:8000/api/tests?limit=50&offset=0"

# Bad (all at once):
curl "http://localhost:8000/api/tests"
```

---

## Need Help?

### Check These Files

1. **Server Logs** — Shows ingestion progress and errors
2. **verify_system.py** — Run to check all systems
3. **allure_connector.py** — Path handling logic (already fixed)
4. **data_loader.py** — Table creation logic

### Key Files

| File | Purpose |
|------|---------|
| `universal_ingester/connectors/allure_connector.py` | Reads Allure data (path fixed!) |
| `services/data_loader.py` | Creates DuckDB tables |
| `services/main.py` | FastAPI server |
| `verify_system.py` | System verification |

---

## Summary

| Issue | Cause | Fix |
|-------|-------|-----|
| `flattened_tests` doesn't exist | Ingestion failed | Restart ingestion with correct path |
| Path validation fails | Spaces/special chars in path | Use path without spaces, or use fixed version |
| Dashboard slow | No indexes | Create indexes after ingestion |
| API slow | Large payloads | Use pagination |

---

## Still Having Issues?

1. **Run verification**: `python verify_system.py`
2. **Check server logs** for ERROR messages
3. **Verify Allure path** exists and has `-result.json` files
4. **Restart server** and retry ingestion
5. **Clear cache** and start fresh if needed

**All fixes have been applied. System should work now!** ✅
