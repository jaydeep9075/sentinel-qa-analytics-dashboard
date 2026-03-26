from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import lancedb
import duckdb
import pandas as pd
import os
import uuid
import datetime
import json
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
os.makedirs(DB_PATH, exist_ok=True)
db = lancedb.connect(DB_PATH)
ctx_manager = SentinelContextManager()

# ✅ Schema Pinning: Pre-defining the structure to save tokens
TEST_SCHEMA_INFO = "Columns: [test_name, status, duration, error_message, module, timestamp]"

def init_db():
    try:
        if "saved_charts" not in db.list_tables():
            db.create_table("saved_charts", data=[{
                "id": "initial", "prompt": "initial", "chart_type": "none", 
                "config": "{}", "created_at": str(datetime.datetime.now())
            }])
    except Exception as e:
        if "already exists" not in str(e): print(f"DB Init Warning: {e}")

init_db()

GEMINI_KEY = "AIzaSyC3OQz4WV23WrocKomVN7vD-k5pGq8eyPE"
client = genai.Client(api_key=GEMINI_KEY)

class ChatReq(BaseModel):
    message: str

def run_local_query(sql: str):
    con = duckdb.connect()
    con.execute("INSTALL lance; LOAD lance;")
    return con.execute(sql).df()

# --- 1. Persistence Endpoints ---

@app.get("/ai/generated-charts")
def get_charts():
    table = db.open_table("saved_charts")
    df = table.to_pandas()
    charts = df[df.id != "initial"].to_dict(orient="records")
    for c in charts:
        if isinstance(c['config'], str):
            try: c['config'] = json.loads(c['config'])
            except: pass
    return {"charts": sorted(charts, key=lambda x: x['created_at'], reverse=True)}

@app.delete("/ai/chart/{chart_id}")
def delete_chart(chart_id: str):
    db.open_table("saved_charts").delete(f"id = '{chart_id}'")
    return {"success": True}

# --- 2. Optimized AI Chat (Token Efficient) ---

@app.post("/ai/chat")
async def api_chat(req: ChatReq):
    user_msg = req.message.lower()
    ctx_manager.add_message("user", user_msg)
    
    # Efficient Retrieval: Only get what is needed
    try:
        if any(word in user_msg for word in ["slow", "top", "avg"]):
            sql = f"SELECT test_name, duration FROM '{DB_PATH}/local_test_results.lance' ORDER BY duration DESC LIMIT 5"
            df = run_local_query(sql)
        else:
            table = db.open_table("local_test_results")
            df = table.search(user_msg).limit(3).to_pandas()[['test_name', 'status', 'error_message']]
        
        # Markdown is the most token-efficient way to represent structured data
        data_context = df.to_markdown(index=False)
    except:
        data_context = "No data found."

    # System Instruction is pinned to save tokens on every turn
    system_prompt = f"""
    Role: Sentinel QA AI. 
    Context Schema: {TEST_SCHEMA_INFO}
    Data:
    {data_context}
    
    Task: Answer concisely based ONLY on the data above.
    """
    
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=system_prompt)
        ai_text = response.text
        ctx_manager.add_message("assistant", ai_text)
        return {"response": ai_text}
    except Exception as e:
        return {"response": f"AI Error: {str(e)}"}

# --- 3. Chart Generation ---

@app.post("/ai/generate-chart")
async def api_gen_chart(req: ChatReq):
    try:
        df = run_local_query(f"SELECT * FROM '{DB_PATH}/local_test_results.lance'")
        
        # Send only a 3-row sample to save tokens
        prompt = f"Schema: {TEST_SCHEMA_INFO}. Sample: {df.head(3).to_json()}. User Request: {req.message}. Return ONLY raw ApexCharts JSON."
        
        res = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        clean_json = res.text.replace("```json", "").replace("```", "").strip()
        chart_config = json.loads(clean_json)

        new_id = str(uuid.uuid4())
        db.open_table("saved_charts").add([{
            "id": new_id, "prompt": req.message, "chart_type": "bar", 
            "config": clean_json, "created_at": str(datetime.datetime.now())
        }])
        
        return {"success": True, "config": chart_config, "id": new_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)