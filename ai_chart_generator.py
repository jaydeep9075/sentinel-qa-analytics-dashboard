import json
import pandas as pd
import numpy as np
import re
import uuid
from datetime import datetime
import os

class AIChartGenerator:
    def __init__(self, master_file_path):
        self.master_file_path = master_file_path
        self.data = self.load_data()
        self.df = self.prepare_dataframe()
        self.charts_storage = "generated_charts.json"
        self.load_charts_storage()
    
    def load_data(self):
        with open(self.master_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def prepare_dataframe(self):
        """Prepare dataframe from tests data"""
        df = pd.DataFrame(self.data.get("tests", []))
        
        # Add derived columns for better analysis
        if not df.empty and "timestamp" in df.columns:
            df["date"] = pd.to_datetime(df["timestamp"], unit='ms')
            df["hour"] = df["date"].dt.hour
            df["day"] = df["date"].dt.day
            df["month"] = df["date"].dt.month
        
        return df
    
    def load_charts_storage(self):
        """Load or create charts storage"""
        if os.path.exists(self.charts_storage):
            with open(self.charts_storage, 'r') as f:
                self.charts = json.load(f)
        else:
            self.charts = []
    
    def save_charts_storage(self):
        """Save charts to storage"""
        with open(self.charts_storage, 'w') as f:
            json.dump(self.charts, f, indent=2)
    
    def extract_chart_config(self, response_text):
        """Extract chart configuration from AI response"""
        # Try to find JSON in the response
        json_pattern = r'\{[\s\S]*\}'
        matches = re.findall(json_pattern, response_text)
        
        for match in matches:
            try:
                config = json.loads(match)
                if self.validate_chart_config(config):
                    return config
            except:
                continue
        
        # If no JSON found, try to parse natural language response
        return self.parse_natural_language_response(response_text)
    
    def validate_chart_config(self, config):
        """Validate if config has required chart structure"""
        required_keys = ['series', 'options']
        if all(key in config for key in required_keys):
            return True
        
        # Alternative structure
        if 'type' in config and 'data' in config:
            return True
        
        return False
    
    def parse_natural_language_response(self, text):
        """Parse natural language response into chart config"""
        text_lower = text.lower()
        
        # Determine chart type
        chart_type = 'bar'  # default
        if 'pie' in text_lower:
            chart_type = 'pie'
        elif 'line' in text_lower:
            chart_type = 'line'
        elif 'heatmap' in text_lower:
            chart_type = 'heatmap'
        elif 'scatter' in text_lower:
            chart_type = 'scatter'
        elif 'area' in text_lower:
            chart_type = 'area'
        
        # Create basic config
        return self.create_basic_chart_config(chart_type)
    
    def create_basic_chart_config(self, chart_type):
        """Create a basic chart configuration based on the data"""
        if self.df.empty:
            return None
        
        config = {
            "type": chart_type,
            "series": [],
            "options": {
                "chart": {
                    "type": chart_type,
                    "height": 350,
                    "toolbar": {
                        "show": True
                    }
                },
                "title": {
                    "text": f"AI Generated {chart_type.title()} Chart",
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
                    "borderColor": "#e7e7e7",
                    "row": {
                        "colors": ["#f3f3f3", "transparent"],
                        "opacity": 0.5
                    }
                },
                "xaxis": {
                    "type": "category"
                },
                "legend": {
                    "position": "top",
                    "horizontalAlign": "right",
                    "floating": True,
                    "offsetY": -25,
                    "offsetX": -5
                }
            }
        }
        
        # Add data based on chart type
        if chart_type == 'pie':
            # Status distribution for pie chart
            status_counts = self.df['status'].value_counts()
            config["series"] = status_counts.values.tolist()
            config["options"]["labels"] = status_counts.index.tolist()
            config["options"]["title"]["text"] = "Test Status Distribution"
        
        elif chart_type == 'bar':
            # Module-wise test counts
            module_stats = self.df.groupby('module')['status'].value_counts().unstack().fillna(0)
            config["series"] = []
            for status in ['passed', 'failed']:
                if status in module_stats.columns:
                    config["series"].append({
                        "name": status.title(),
                        "data": module_stats[status].tolist()
                    })
            config["options"]["xaxis"]["categories"] = module_stats.index.tolist()
            config["options"]["title"]["text"] = "Module-wise Test Results"
        
        elif chart_type == 'line':
            # Trend over time
            if 'timestamp' in self.df.columns:
                df_sorted = self.df.sort_values('timestamp')
                df_sorted['cumulative_passed'] = (df_sorted['status'] == 'passed').cumsum()
                df_sorted['cumulative_failed'] = (df_sorted['status'] == 'failed').cumsum()
                
                config["series"] = [
                    {
                        "name": "Passed",
                        "data": df_sorted['cumulative_passed'].tolist()
                    },
                    {
                        "name": "Failed",
                        "data": df_sorted['cumulative_failed'].tolist()
                    }
                ]
                config["options"]["xaxis"]["categories"] = list(range(len(df_sorted)))
                config["options"]["title"]["text"] = "Cumulative Test Results Over Time"
        
        return config
    
    def generate_chart(self, prompt):
        """Generate chart configuration using Ollama"""
        
        # Prepare data sample for AI
        data_sample = self.df.head(20).to_json(orient='records')
        
        # Get available columns
        columns = list(self.df.columns)
        
        # Create AI prompt
        ai_prompt = f"""
You are a QA data visualization expert. Generate a chart configuration based on the user's request.

Available data columns: {columns}
Data sample: {data_sample}

User request: {prompt}

Generate a chart configuration in JSON format with the following structure:
{{
    "type": "chart_type",  // one of: bar, line, pie, donut, area, scatter, heatmap, radar, radialBar
    "series": [],  // data series for the chart
    "options": {{  // chart options including title, xaxis, yaxis, colors, etc.
        "chart": {{
            "type": "chart_type",
            "height": 350
        }},
        "title": {{
            "text": "Chart Title"
        }},
        "xaxis": {{
            "categories": []  // x-axis labels if applicable
        }},
        "colors": [],  // optional color scheme
        "dataLabels": {{
            "enabled": true
        }}
    }}
}}

Rules:
1. Use ONLY the real data provided
2. Make sure the chart is meaningful and readable
3. Include appropriate labels and titles
4. Use professional color schemes
5. Return ONLY the JSON configuration, no explanations

JSON Configuration:
"""
        
        try:
            # Call Ollama
            response = ollama.chat(
                model="qwen2.5-coder:7b",  # or use "llama2" or "mistral"
                messages=[{"role": "user", "content": ai_prompt}]
            )
            
            response_text = response["message"]["content"]
            
            # Extract chart configuration
            chart_config = self.extract_chart_config(response_text)
            
            if not chart_config:
                # Fallback to basic config
                chart_config = self.create_basic_chart_config('bar')
            
            # Generate unique ID for the chart
            chart_id = str(uuid.uuid4())
            
            # Create chart entry
            chart_entry = {
                "id": chart_id,
                "prompt": prompt,
                "chart_type": chart_config.get("type", "bar"),
                "config": chart_config,
                "created_at": datetime.now().isoformat()
            }
            
            # Save to storage
            self.charts.append(chart_entry)
            self.save_charts_storage()
            
            return {
                "success": True,
                "chart_id": chart_id,
                "config": chart_config
            }
            
        except Exception as e:
            print(f"Error generating chart: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_all_charts(self):
        """Get all generated charts"""
        return self.charts
    
    def delete_chart(self, chart_id):
        """Delete a chart by ID"""
        self.charts = [c for c in self.charts if c["id"] != chart_id]
        self.save_charts_storage()
        return True

# Initialize the generator
generator = AIChartGenerator("qa_analytics_master.json")