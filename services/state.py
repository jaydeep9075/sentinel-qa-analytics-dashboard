from collections import OrderedDict

# Global state that holds connections for the currently active ingestion.
# `_ingestion_pool` keeps a small LRU of recently used ingestions warm (see
# data_loader.ensure_ingestion_loaded) so switching between a handful of
# builds doesn't pay a full reload every time; lance_db/duck_conn/embedder/
# current_ingestion_id always point at whichever entry is currently active.
lance_db = None
duck_conn = None
embedder = None
current_ingestion_id = None
_ingestion_pool: "OrderedDict[str, dict]" = OrderedDict()

# RBA: project and role managers (initialized lazily)
project_manager = None
role_manager = None

# LLM usage counters (runtime totals since backend start)
token_usage = {
	"prompt_tokens": 0,
	"completion_tokens": 0,
	"total_tokens": 0,
	"calls": 0,
}
token_usage_by_model = {}