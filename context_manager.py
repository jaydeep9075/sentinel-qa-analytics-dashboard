import json
import os
from datetime import datetime

class SentinelContextManager:
    def __init__(self, history_file="chat_history.json"):
        self.history_file = history_file
        # Initial state structure
        self.state = self._load_history()

    def _load_history(self):
        """Loads existing history or creates a fresh one."""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    return json.load(f)
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
            }
        }

    def add_message(self, role, content):
        """Adds a message to the sliding window (keeps history short for tokens)."""
        self.state["sessions"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        # Keep only last 10 messages to save tokens
        if len(self.state["sessions"]) > 10:
            self.state["sessions"].pop(0)
        self._save()

    def update_context(self, table=None, build_id=None, env=None):
        """Updates the active focus of the AI."""
        if table: self.state["current_context"]["last_table"] = table
        if build_id: self.state["current_context"]["last_build_id"] = build_id
        if env: self.state["current_context"]["environment"] = env
        self._save()

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