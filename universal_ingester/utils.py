# utils.py
from typing import List

# Single source of truth for the embedding model name - imported by anything
# else in the app that needs to embed text with the same model ingestion
# used (e.g. services/project_manager.py), so a future change can't silently
# desync one call site from another and produce a dimensionality mismatch
# against already-embedded LanceDB tables.
#
# Deliberately a free, local sentence-transformers model rather than a
# hosted embedding API tied to whichever chat LLM_PROVIDER is configured:
#   - Anthropic (a fully-supported chat provider in this app) has no public
#     embeddings API at all - tying embeddings to "whatever chat provider is
#     configured" would leave ingestion's semantic-search feature completely
#     broken for any deployer who picks Anthropic.
#   - Zero ongoing API cost regardless of ingestion volume - embedding cost
#     scales with DATA size (potentially thousands of chunks per ingest),
#     not query volume, so a hosted API here would work against this app's
#     own token-efficiency goal far more than the chat/answer LLM calls do.
#   - No network dependency/rate-limiting during ingestion.
# bge-small-en-v1.5 is a meaningfully better free/local retrieval model than
# the older MiniLM default at nearly the same size/speed (~130MB, still
# 384-dim, CPU-friendly) - see MTEB retrieval benchmarks. Admins who want an
# even lighter or higher-quality option can still pick from
# services/app_settings.py's configurable embedding_model setting.
DEFAULT_EMBEDDING_MODEL = 'BAAI/bge-small-en-v1.5'


class EmbeddingGenerator:
    def __init__(self, model_name=DEFAULT_EMBEDDING_MODEL):
        # Lazy import so backend can start even if sentence-transformers is unavailable.
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        try:
            self.dim = self.model.get_embedding_dimension()
        except AttributeError:
            self.dim = self.model.get_sentence_embedding_dimension()

    def embed(self, texts: List[str], batch_size=32) -> List[List[float]]:
        embeddings = self.model.encode(texts, batch_size=batch_size, show_progress_bar=False)
        return embeddings.tolist()