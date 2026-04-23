# Global state that holds connections for the currently active ingestion.
# For simplicity, we'll reinitialize per request based on ingestion_id header.
lance_db = None
duck_conn = None
embedder = None
current_ingestion_id = None

# RBA: project and role managers (initialized lazily)
project_manager = None
role_manager = None