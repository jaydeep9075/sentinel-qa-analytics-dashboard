import json
import os
from datetime import datetime

class SentinelContextManager:
    def __init__(self, history_file="chat_history.json"):
        self.history_file = history_file
        self.state = self._load_history()

    def _load_history(self):
        """Loads existing history or creates a fresh one."""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    state = json.load(f)
                    # Ensure required keys exist for backward compatibility
                    if "query_results" not in state:
                        state["query_results"] = {}
                    if "sessions" not in state:
                        state["sessions"] = []
                    if "current_context" not in state:
                        state["current_context"] = {
                            "last_table": None,
                            "last_build_id": None,
                            "environment": "ALL",
                            "focus_area": None
                        }
                    return state
            except:
                return self._get_empty_state()
        return self._get_empty_state()

    def _get_empty_state(self):
        return {
            "sessions": [],
            "current_context": {
                "last_table": None,
                "last_build_id": None,
                "environment": "ALL",
                "focus_area": None
            },
            "query_results": {}  # New key for storing query results
        }

    def add_message(self, role, content):
        """Adds a message to the sliding window."""
        self.state["sessions"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        # Keep only last 20 messages for better context
        if len(self.state["sessions"]) > 20:
            self.state["sessions"].pop(0)
        self._save()

    def update_context(self, table=None, build_id=None, env=None):
        """Updates the active focus of the AI."""
        if table: self.state["current_context"]["last_table"] = table
        if build_id: self.state["current_context"]["last_build_id"] = build_id
        if env: self.state["current_context"]["environment"] = env
        self._save()

    def store_query_result(self, query_key, result_data):
        """Store query results for later reference."""
        if "query_results" not in self.state:
            self.state["query_results"] = {}
        self.state["query_results"][query_key] = {
            "timestamp": datetime.now().isoformat(),
            "data": result_data
        }
        # Keep only last 5 results to avoid memory bloat
        if len(self.state["query_results"]) > 5:
            oldest = min(self.state["query_results"].keys(), key=lambda k: self.state["query_results"][k]["timestamp"])
            del self.state["query_results"][oldest]
        self._save()

    def get_last_query_result(self):
        """Get the most recent query result."""
        if "query_results" not in self.state or not self.state["query_results"]:
            return None
        last_key = max(self.state["query_results"].keys(), key=lambda k: self.state["query_results"][k]["timestamp"])
        return self.state["query_results"][last_key]["data"]

    def get_full_context_string(self):
        """Returns a string for the LLM System Prompt."""
        ctx = self.state["current_context"]
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in self.state["sessions"]])
        return f"""
CURRENT SYSTEM CONTEXT:
- Active Table: {ctx['last_table']}
- Filtered Build: {ctx['last_build_id']}
- Environment: {ctx['environment']}

RECENT CONVERSATION:
{history_text}
"""

    def _save(self):
        with open(self.history_file, 'w') as f:
            json.dump(self.state, f, indent=4)