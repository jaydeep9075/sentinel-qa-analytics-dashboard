# utils.py
from typing import List

class EmbeddingGenerator:
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        # Lazy import so backend can start even if sentence-transformers is unavailable.
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)
        try:
            self.dim = self.model.get_embedding_dimension()
        except AttributeError:
            self.dim = self.model.get_sentence_embedding_dimension()

    def embed(self, texts: List[str], batch_size=32) -> List[List[float]]:
        embeddings = self.model.encode(texts, batch_size=batch_size, show_progress_bar=False)
        return embeddings.tolist()