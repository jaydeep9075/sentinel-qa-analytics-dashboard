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

# ✅ Initialization & Persistence Setup
DB_PATH = "./sentinel_data"
os.makedirs(DB_PATH, exist_ok=True)
db = lancedb.connect(DB_PATH)
ctx_manager = SentinelContextManager()

# --- Robust DB Initialization ---
def initialize_tables():
    table_name = "saved_charts"
    existing_tables = db.list_tables()
    
    if table_name not in existing_tables:
        try:
            db.create_table(table_name, data=[{
                "id": "initial", 
                "prompt": "initial", 
                "chart_type": "none", 
                "config": "{}", 
                "created_at": str(datetime.datetime.now())
            }])
            print(f"✅ Created table: {table_name}")
        except Exception as e:
            # Handle the case where list_tables lied and the table exists
            if "already exists" in str(e).lower():
                print(f"ℹ️ Table {table_name} detected via exception handler.")
            else:
                print(f"❌ Table creation error: {e}")
    else:
        print(f"ℹ️ Table {table_name} verified.")

initialize_tables()

# --- AI Configuration ---
GEMINI_KEY = "AIzaSyDVie3B1xMTyOa5-uqTwqA0-UpkXkOfeVc"
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
    # Filter out the init row and convert JSON strings back to dicts
    charts = df[df.id != "initial"].to_dict(orient="records")
    for c in charts:
        if isinstance(c['config'], str):
            try:
                c['config'] = json.loads(c['config'])
            except:
                pass
    return {"charts": sorted(charts, key=lambda x: x['created_at'], reverse=True)}

@app.delete("/ai/chart/{chart_id}")
def delete_chart(chart_id: str):
    table = db.open_table("saved_charts")
    table.delete(f"id = '{chart_id}'")
    return {"success": True}

# --- 2. Analytics Endpoints ---

@app.get("/kpis")
def get_kpis():
    try:
        df = run_local_query(f"SELECT status, duration FROM '{DB_PATH}/local_test_results.lance'")
        return {
            "total": len(df),
            "passed": int((df.status == 'passed').sum()),
            "failed": int((df.status == 'failed').sum()),
            "avg_duration": round(df.duration.mean(), 2) if not df.empty else 0
        }
    except Exception:
        return {"total": 0, "passed": 0, "failed": 0, "avg_duration": 0}

# --- 3. Optimized AI RAG Chat ---

@app.post("/ai/chat")
async def api_chat(req: ChatReq):
    user_msg = req.message.lower()
    ctx_manager.add_message("user", user_msg)
    
    try:
        if any(word in user_msg for word in ["slow", "top", "fastest", "average"]):
            sql = f"SELECT test_name, AVG(duration) as avg_dur FROM '{DB_PATH}/local_test_results.lance' GROUP BY test_name ORDER BY avg_dur DESC LIMIT 10"
            df = run_local_query(sql)
        else:
            table = db.open_table("local_test_results")
            df = table.search(user_msg).limit(5).to_pandas()
        data_context = df.to_markdown(index=False)
    except:
        data_context = "No specific test data available."

    system_prompt = f"Context:\n{data_context}\n\nUser Question: {req.message}\nAnswer as Sentinel QA AI."
    
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=system_prompt)
        ai_text = response.text
        ctx_manager.add_message("assistant", ai_text)
        return {"response": ai_text}
    except Exception as e:
        return {"response": f"AI Error: {str(e)}"}

# --- 4. Chart Generation with Persistence ---

@app.post("/ai/generate-chart")
async def api_gen_chart(req: ChatReq):
    user_prompt = req.message 
    
    try:
        df = run_local_query(f"SELECT * FROM '{DB_PATH}/local_test_results.lance'")
        data_sample = df.head(5).to_markdown(index=False)
        
        prompt = f"""
        Columns: {list(df.columns)}
        Sample Data: {data_sample}
        User Request: {user_prompt}
        Return ONLY a JSON object for ApexCharts. Do not include markdown or backticks.
        """
        
        res = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        clean_json = res.text.replace("```json", "").replace("```", "").strip()
        chart_config = json.loads(clean_json)

        new_chart_id = str(uuid.uuid4())
        db.open_table("saved_charts").add([{
            "id": new_chart_id,
            "prompt": user_prompt,
            "chart_type": chart_config.get('chart', {}).get('type', 'bar'),
            "config": clean_json,
            "created_at": str(datetime.datetime.now())
        }])
        
        return {"success": True, "config": chart_config, "id": new_chart_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)