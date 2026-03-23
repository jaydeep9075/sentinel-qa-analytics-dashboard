# gemini_qa_api.py - Single file with Gemini AI integration
import json
import pandas as pd
import numpy as np
import re
import uuid
from datetime import datetime
import os
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ============================================
# AI Chart Generator Class (with Gemini & Demo)
# ============================================


class AIChartGenerator:
    def __init__(self, master_file_path: str, gemini_api_key: Optional[str] = None):
        """
        Initialize chart generator with Gemini AI or demo mode
        
        Args:
            master_file_path: Path to QA analytics master JSON file
            gemini_api_key: Optional Gemini API key (uses demo mode if not provided)
        """
        self.master_file_path = master_file_path
        self.data = self.load_data()
        self.df = self.prepare_dataframe()
        self.charts_storage = "generated_charts.json"
        self.gemini_api_key = gemini_api_key
        self.use_gemini = gemini_api_key is not None
        
        # Try to import Gemini if API key is provided
        if self.use_gemini:
            try:
                import google.generativeai as genai
                genai.configure(api_key=gemini_api_key)
                self.model = genai.GenerativeModel('gemini-1.5-flash')
                print("✅ Gemini AI initialized successfully")
            except Exception as e:
                print(f"⚠️ Failed to initialize Gemini: {e}")
                print("🔄 Falling back to demo mode")
                self.use_gemini = False
        else:
            print("ℹ️ No Gemini API key provided - using demo mode")
        
        self.load_charts_storage()
    
    def load_data(self) -> Dict:
        """Load data from master file"""
        try:
            with open(self.master_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Warning: {self.master_file_path} not found. Creating demo data.")
            return self.create_demo_data()
    
    def create_demo_data(self) -> Dict:
        """Create demo data for testing"""
        modules = ['auth', 'api', 'ui', 'database', 'performance']
        statuses = ['passed', 'failed']
        
        tests = []
        for i in range(100):
            test = {
                "id": f"test_{i}",
                "name": f"Test Case {i}",
                "status": np.random.choice(statuses, p=[0.85, 0.15]),
                "duration_sec": round(np.random.uniform(0.5, 12.0), 2),
                "module": np.random.choice(modules),
                "timestamp": int(datetime.now().timestamp() * 1000) - np.random.randint(0, 30) * 86400000
            }
            tests.append(test)
        
        # Calculate module stability
        module_stability = {}
        for module in modules:
            module_tests = [t for t in tests if t['module'] == module]
            if module_tests:
                pass_rate = sum(1 for t in module_tests if t['status'] == 'passed') / len(module_tests)
                module_stability[module] = {
                    "pass_rate": round(pass_rate * 100, 2),
                    "total_tests": len(module_tests),
                    "failed_tests": sum(1 for t in module_tests if t['status'] == 'failed'),
                    "avg_duration": round(np.mean([t['duration_sec'] for t in module_tests]), 2)
                }
        
        # Calculate slow tests (top 10 by duration)
        slow_tests = sorted(tests, key=lambda x: x['duration_sec'], reverse=True)[:10]
        
        # Calculate history trend
        trend_data = []
        for i in range(30):
            day_tests = [t for t in tests if t['timestamp'] > datetime.now().timestamp() * 1000 - (30-i)*86400000]
            trend_data.append({
                "date": (datetime.now() - pd.Timedelta(days=30-i)).strftime("%Y-%m-%d"),
                "passed": sum(1 for t in day_tests if t['status'] == 'passed'),
                "failed": sum(1 for t in day_tests if t['status'] == 'failed')
            })
        
        return {
            "tests": tests,
            "analytics": {
                "module_stability": module_stability,
                "slow_tests": slow_tests
            },
            "trends": {
                "history-trend": trend_data
            }
        }
    
    def prepare_dataframe(self) -> pd.DataFrame:
        """Prepare dataframe from tests data"""
        df = pd.DataFrame(self.data.get("tests", []))
        
        # Add derived columns for better analysis
        if not df.empty and "timestamp" in df.columns:
            df["date"] = pd.to_datetime(df["timestamp"], unit='ms')
            df["hour"] = df["date"].dt.hour
            df["day"] = df["date"].dt.day
            df["month"] = df["date"].dt.month
            df["day_of_week"] = df["date"].dt.day_name()
        
        return df
    
    def load_charts_storage(self):
        """Load or create charts storage"""
        if os.path.exists(self.charts_storage):
            try:
                with open(self.charts_storage, 'r') as f:
                    self.charts = json.load(f)
            except:
                self.charts = []
        else:
            self.charts = []
    
    def save_charts_storage(self):
        """Save charts to storage"""
        with open(self.charts_storage, 'w') as f:
            json.dump(self.charts, f, indent=2)
    
    def generate_demo_response(self, prompt: str) -> Dict:
        """Generate intelligent demo response without API calls"""
        prompt_lower = prompt.lower()
        
        # Determine chart type from prompt
        if any(word in prompt_lower for word in ['trend', 'over time', 'history', 'cumulative', 'timeline']):
            chart_type = 'line'
            title = "Test Results Trend Over Time"
            categories = [f"Day {i+1}" for i in range(min(10, len(self.df)))]
            
            if 'timestamp' in self.df.columns:
                df_sorted = self.df.sort_values('timestamp').head(10)
                passed_data = (df_sorted['status'] == 'passed').cumsum().tolist()
                failed_data = (df_sorted['status'] == 'failed').cumsum().tolist()
            else:
                passed_data = list(range(1, len(self.df[:10]) + 1))
                failed_data = [0] * len(self.df[:10])
            
            series = [
                {"name": "Passed", "data": passed_data},
                {"name": "Failed", "data": failed_data}
            ]
        
        elif any(word in prompt_lower for word in ['distribution', 'percentage', 'proportion', 'pie']):
            chart_type = 'pie'
            title = "Test Status Distribution"
            status_counts = self.df['status'].value_counts()
            series = status_counts.values.tolist()
            labels = status_counts.index.tolist()
        
        elif any(word in prompt_lower for word in ['module', 'component', 'by module']):
            chart_type = 'bar'
            title = "Test Results by Module"
            module_stats = self.df.groupby('module')['status'].value_counts().unstack().fillna(0)
            
            series = []
            for status in ['passed', 'failed']:
                if status in module_stats.columns:
                    series.append({
                        "name": status.title(),
                        "data": module_stats[status].tolist()
                    })
            categories = module_stats.index.tolist()
        
        elif any(word in prompt_lower for word in ['duration', 'slow', 'time', 'performance']):
            chart_type = 'bar'
            title = "Slowest Tests by Duration"
            slow_tests = self.df.nlargest(10, 'duration_sec')
            series = [{
                "name": "Duration (seconds)",
                "data": slow_tests['duration_sec'].tolist()
            }]
            categories = slow_tests['name'].tolist() if 'name' in slow_tests.columns else [f"Test {i+1}" for i in range(len(slow_tests))]
        
        else:
            # Default to bar chart
            chart_type = 'bar'
            title = "Test Results Overview"
            status_counts = self.df['status'].value_counts()
            series = [{
                "name": "Count",
                "data": status_counts.values.tolist()
            }]
            categories = status_counts.index.tolist()
        
        # Build configuration
        config = {
            "type": chart_type,
            "series": series,
            "options": {
                "chart": {
                    "type": chart_type,
                    "height": 350,
                    "toolbar": {
                        "show": True
                    }
                },
                "title": {
                    "text": title,
                    "align": "center"
                },
                "dataLabels": {
                    "enabled": True
                },
                "stroke": {
                    "curve": "smooth",
                    "width": 2
                },
                "grid": {
                    "borderColor": "#e7e7e7"
                },
                "xaxis": {
                    "categories": categories if 'categories' in locals() else list(range(len(series[0]['data'])))
                },
                "yaxis": {
                    "title": {
                        "text": "Count"
                    }
                },
                "legend": {
                    "position": "top",
                    "horizontalAlign": "center"
                }
            }
        }
        
        # Add labels for pie chart
        if chart_type == 'pie' and 'labels' in locals():
            config["options"]["labels"] = labels
        
        return config
    
    def generate_chart(self, prompt: str) -> Dict[str, Any]:
        """Generate chart configuration using Gemini or demo mode"""
        
        if self.use_gemini:
            # Use Gemini API
            try:
                # Prepare data summary
                data_summary = {
                    "total_tests": len(self.df),
                    "columns": list(self.df.columns),
                    "status_counts": self.df['status'].value_counts().to_dict() if 'status' in self.df.columns else {},
                    "modules": self.df['module'].unique().tolist() if 'module' in self.df.columns else [],
                    "sample_data": self.df.head(5).to_dict('records')
                }
                
                ai_prompt = f"""
You are a QA data visualization expert. Generate a chart configuration based on the user's request.

Data Summary: {json.dumps(data_summary, indent=2)}

User Request: {prompt}

Generate a complete ApexCharts configuration in JSON format with this structure:
{{
    "type": "bar/line/pie/donut/area",
    "series": [],
    "options": {{
        "chart": {{"type": "chart_type", "height": 350}},
        "title": {{"text": "Title", "align": "center"}},
        "xaxis": {{"categories": []}},
        "yaxis": {{"title": {{"text": "Label"}}}},
        "dataLabels": {{"enabled": true}}
    }}
}}

Use ONLY the real data. Return ONLY the JSON configuration.
"""
                
                response = self.model.generate_content(ai_prompt)
                response_text = response.text
                
                # Extract JSON from response
                json_match = re.search(r'\{[\s\S]*\}', response_text)
                if json_match:
                    chart_config = json.loads(json_match.group())
                else:
                    chart_config = self.generate_demo_response(prompt)
                    
            except Exception as e:
                print(f"⚠️ Gemini API error: {e}")
                chart_config = self.generate_demo_response(prompt)
        else:
            # Use demo mode
            chart_config = self.generate_demo_response(prompt)
        
        # Ensure we have a valid config
        if not chart_config:
            chart_config = self.generate_demo_response(prompt)
        
        # Generate unique ID for the chart
        chart_id = str(uuid.uuid4())
        
        # Create chart entry
        chart_entry = {
            "id": chart_id,
            "prompt": prompt,
            "chart_type": chart_config.get("type", "bar"),
            "config": chart_config,
            "created_at": datetime.now().isoformat(),
            "model": "gemini" if self.use_gemini else "demo"
        }
        
        # Save to storage
        self.charts.append(chart_entry)
        self.save_charts_storage()
        
        return {
            "success": True,
            "chart_id": chart_id,
            "config": chart_config
        }
    
    def get_all_charts(self) -> list:
        """Get all generated charts"""
        return self.charts
    
    def delete_chart(self, chart_id: str) -> bool:
        """Delete a chart by ID"""
        self.charts = [c for c in self.charts if c["id"] != chart_id]
        self.save_charts_storage()
        return True
    
    def get_chart_stats(self) -> Dict:
        """Get statistics about generated charts"""
        if not self.charts:
            return {"total": 0, "by_type": {}, "by_date": []}
        
        chart_types = {}
        for chart in self.charts:
            chart_type = chart.get("chart_type", "unknown")
            chart_types[chart_type] = chart_types.get(chart_type, 0) + 1
        
        dates = [chart["created_at"] for chart in self.charts]
        
        return {
            "total": len(self.charts),
            "by_type": chart_types,
            "oldest": min(dates) if dates else None,
            "newest": max(dates) if dates else None
        }


# ============================================
# FastAPI Application
# ============================================

app = FastAPI(title="QA Analytics API with AI Chart Generation")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class ChartRequest(BaseModel):
    prompt: str

class ChartResponse(BaseModel):
    success: bool
    chart_id: Optional[str] = None
    config: Optional[dict] = None
    error: Optional[str] = None

# File paths
BASE_DIR = os.path.dirname(__file__)
MASTER_FILE = os.path.join(BASE_DIR, "qa_analytics_master.json")

# Initialize generator with Gemini API key if available
GEMINI_API_KEY = "api key here"
generator = AIChartGenerator(MASTER_FILE, GEMINI_API_KEY)

def load_data():
    """Load data from master file"""
    with open(MASTER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# ============================================
# Analytics Endpoints
# ============================================

@app.get("/kpis")
def get_kpis():
    """Get key performance indicators"""
    data = load_data()
    df = pd.DataFrame(data["tests"])
    
    return {
        "total": len(df),
        "passed": int((df.status == "passed").sum()),
        "failed": int((df.status == "failed").sum()),
        "avg_duration": round(df.duration_sec.mean(), 2),
    }

@app.get("/status-distribution")
def status_distribution():
    """Get test status distribution"""
    data = load_data()
    df = pd.DataFrame(data["tests"])
    return df.groupby("status").size().to_dict()

@app.get("/module-stability")
def module_stability():
    """Get module stability metrics"""
    data = load_data()
    return data["analytics"]["module_stability"]

@app.get("/slow-tests")
def slow_tests():
    """Get slowest tests"""
    data = load_data()
    return data["analytics"]["slow_tests"]

@app.get("/history-trend")
def history_trend():
    """Get historical trends"""
    data = load_data()
    return data["trends"]["history-trend"]

@app.get("/failures")
def failures():
    """Get failed tests"""
    data = load_data()
    df = pd.DataFrame(data["tests"])
    failures = df[df.status == "failed"]
    return failures.to_dict(orient="records")

# ============================================
# AI Chart Generation Endpoints
# ============================================

@app.post("/ai/generate-chart", response_model=ChartResponse)
async def generate_chart(request: ChartRequest):
    """Generate a chart based on user prompt"""
    try:
        result = generator.generate_chart(request.prompt)
        return ChartResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ai/generated-charts")
async def get_generated_charts():
    """Get all generated charts"""
    try:
        charts = generator.get_all_charts()
        return {"charts": charts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/ai/chart/{chart_id}")
async def delete_chart(chart_id: str):
    """Delete a generated chart"""
    try:
        generator.delete_chart(chart_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ai/chart-stats")
async def get_chart_stats():
    """Get statistics about generated charts"""
    try:
        stats = generator.get_chart_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ai/status")
async def get_ai_status():
    """Get AI service status"""
    return {
        "mode": "gemini" if generator.use_gemini else "demo",
        "available": True,
        "total_charts": len(generator.charts)
    }

# ============================================
# Main Entry Point
# ============================================

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 Starting QA Analytics API with AI Chart Generation")
    print("=" * 50)
    print(f"📁 Data file: {MASTER_FILE}")
    if GEMINI_API_KEY:
        print("🤖 AI Mode: Gemini (Live API)")
    else:
        print("🎭 AI Mode: Demo Mode (No API key required)")
        print("💡 To use Gemini: Set GEMINI_API_KEY environment variable")
    print("🌐 API URL: http://localhost:8000")
    print("📚 API Docs: http://localhost:8000/docs")
    print("=" * 50)
    print("\n✨ Ready to accept requests!\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)