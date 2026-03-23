import json
import pandas as pd
from typing import List, Dict, Any
from ingestors.base import BaseIngestor

class GenericAIIngestor(BaseIngestor):
    def __init__(self, data_source, gemini_api_key: str):
        """
        data_source: can be a list of dicts (from an API) or a path to a CSV.
        """
        self.data_source = data_source
        self.api_key = gemini_api_key
        
        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-pro')
        
    def fetch_results(self) -> List[Dict[str, Any]]:
        # 1. Load Raw Data
        if isinstance(self.data_source, str) and self.data_source.endswith('.csv'):
            try:
                df = pd.read_csv(self.data_source)
                raw_data = df.to_dict(orient='records')
            except Exception as e:
                print(f"Failed to read CSV: {e}")
                return []
        elif isinstance(self.data_source, list):
            raw_data = self.data_source
        else:
            print("Unsupported data source for GenericAIIngestor")
            return []
            
        if not raw_data:
            return []
            
        sample = raw_data[:3]
        
        # 2. Ask Gemini to map the schema dynamically
        prompt = f"""
You are a data engineering expert. We need to normalize arbitrary QA test data into a strict internal schema.
Internal Strict Schema Fields:
- uuid (string, unique ID)
- name (string, test name)
- module (string, component/suite name)
- status (string, strictly "passed" or "failed")
- duration_sec (float, time taken in seconds)
- error_msg (string)
- timestamp (integer, unix epoch ms)

Here is a sample of the raw data we received from an unknown API/CSV/Excel:
{json.dumps(sample, indent=2)}

Task 1: Map the raw data keys to our internal schema keys. Provide the closest matches.
Task 2: Identify what raw status values equal "passed" and "failed".

Return ONLY a JSON object with this exact structure:
{{
  "key_mapping": {{
     "raw_key_for_id": "uuid",
     "raw_key_for_name": "name",
     "raw_key_for_time": "duration_sec"
     // map other relevant fields as best as you can...
  }},
  "status_mapping": {{
     "raw_pass_value": "passed",
     "raw_fail_value": "failed"
  }}
}}
"""
        response = self.model.generate_content(prompt)
        try:
            # Extract JSON from Gemini
            import re
            json_match = re.search(r'\{[\s\S]*\}', response.text)
            if not json_match:
                raise ValueError("No JSON mapping returned from AI")
                
            mapping = json.loads(json_match.group())
            key_map = mapping.get("key_mapping", {})
            status_map = mapping.get("status_mapping", {})
            print("🤖 AI Dynamic Mapping Generated:")
            print(json.dumps(mapping, indent=2))
        except Exception as e:
            print(f"Failed to generate AI mapping: {e}")
            return []
            
        # 3. Apply AI mapping to the entire dataset (very fast because it runs natively in Python)
        results = []
        for row in raw_data:
            normalized = {
                "uuid": "unknown_id",
                "name": "Unknown Test",
                "module": "General",
                "status": "unknown",
                "duration_sec": 0.0,
                "error_msg": "No Error",
                "timestamp": 0
            }
            
            for raw_key, std_key in key_map.items():
                if raw_key in row and std_key in normalized:
                    val = row[raw_key]
                    if std_key == "status":
                        normalized[std_key] = status_map.get(str(val), "failed") # fallback
                    elif std_key == "duration_sec":
                        try:
                            normalized[std_key] = float(val)
                        except:
                            pass
                    else:
                        normalized[std_key] = val
            results.append(normalized)
            
        return results
