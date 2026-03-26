from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import lancedb
import duckdb
import pandas as pd
import os
from google import genai
from context_manager import SentinelContextManager

app = FastAPI()

# ✅ CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Initialization
DB_PATH = "./sentinel_data"
db = lancedb.connect(DB_PATH)
ctx_manager = SentinelContextManager()
# Use your provided key
GEMINI_KEY = "AIzaSyBTvl5EsJblAJrJiuSWJAKeWOcfRDQxczA"
client = genai.Client(api_key=GEMINI_KEY)

class ChatReq(BaseModel):
    message: str

def run_local_query(sql: str):
    con = duckdb.connect()
    con.execute("INSTALL lance; LOAD lance;")
    return con.execute(sql).df()

# --- KPI Endpoints (Powered by LanceDB) ---
@app.get("/kpis")
def get_kpis():
    df = run_local_query(f"SELECT status, duration FROM '{DB_PATH}/local_test_results.lance'")
    return {
        "total": len(df),
        "passed": int((df.status == 'passed').sum()),
        "failed": int((df.status == 'failed').sum()),
        "avg_duration": round(df.duration.mean(), 2) if not df.empty else 0
    }

# --- The AI RAG Chat Integration ---
@app.post("/ai/chat")
async def api_chat(req: ChatReq):
    user_msg = req.message.lower()
    
    # 1. Update Memory
    ctx_manager.add_message("user", user_msg)
    
    # 2. Hybrid RAG Logic
    # If the user asks for numbers, use DuckDB. If they ask "Why", use Vector Search.
    if any(word in user_msg for word in ["slow", "top", "fastest"]):
        sql = f"SELECT test_name, AVG(duration) as d FROM '{DB_PATH}/local_test_results.lance' GROUP BY test_name ORDER BY d DESC LIMIT 5"
        data_context = run_local_query(sql).to_string()
    else:
        table = db.open_table("local_test_results")
        results = table.search(user_msg).limit(3).to_pandas()
        data_context = results[['test_name', 'status', 'error_message']].to_string()

    # 3. Ask Gemini to explain the retrieved data (RAG)
    system_prompt = f"Data Context:\n{data_context}\n\nUser Question: {user_msg}\nAnswer as Sentinel QA AI."
    
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=system_prompt)
        ai_text = response.text
        ctx_manager.add_message("assistant", ai_text)
        return {"response": ai_text}
    except Exception as e:
        return {"response": f"AI Error: {str(e)}"}

# --- Chart Generation (Merging your Gemini logic) ---
@app.post("/ai/generate-chart")
async def api_gen_chart(req: ChatReq):
    df = run_local_query(f"SELECT * FROM '{DB_PATH}/local_test_results.lance'")
    columns = list(df.columns)
    
    prompt = f"DataFrame columns: {columns}. User request: {req.message}. Return ONLY python code for create_chart(df) returning ApexCharts JSON."
    
    res = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    code = res.text.replace("```python", "").replace("```", "").strip()
    
    local_vars = {}
    exec(code, {'pd': pd}, local_vars)
    chart_config = local_vars['create_chart'](df)
    
    return {"success": True, "config": chart_config}