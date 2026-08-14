import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import lancedb
import pandas as pd
from sentence_transformers import SentenceTransformer
from . import app_settings, config
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

class ProjectManager:
    def __init__(self, projects_root: Path = None):
        self.projects_root = projects_root or Path(config.PROJECTS_ROOT)
        self.projects_root.mkdir(exist_ok=True)
        self._projects_cache = {}
        self._embedder = None
        self._embedder_model = None

    def _get_embedder(self):
        # Re-resolves the effective model on every call and rebuilds if an
        # admin changed it from Settings - same pattern as
        # data_loader._get_shared_embedder(), so this doesn't get left
        # behind as the one embedder that only updates on restart.
        effective_model = app_settings.get_effective_embedding_model()
        if self._embedder is None or self._embedder_model != effective_model:
            self._embedder = SentenceTransformer(effective_model)
            self._embedder_model = effective_model
        return self._embedder

    def list_projects(self) -> List[str]:
        return [p.name for p in self.projects_root.iterdir() 
                if p.is_dir() and (p / "context.md").exists()]

    def load_project(self, project_id: str) -> bool:
        project_path = self.projects_root / project_id
        context_file = project_path / "context.md"
        if not context_file.exists():
            logger.error(f"Project {project_id} missing context.md")
            return False

        content = context_file.read_text(encoding="utf-8")
        summary = self._generate_summary(content, project_id)
        sections = self._split_into_sections(content)
        embeddings_db = self._build_embeddings(project_id, sections)
        criticality = self._load_criticality_map(project_path, content)

        self._projects_cache[project_id] = {
            "summary": summary,
            "embeddings": embeddings_db,
            "criticality": criticality,
        }
        return True

    def _load_summary_fallback(self, project_path: Path) -> Dict:
        """Optional per-project override for when the LLM summary call fails,
        so the fallback isn't hardcoded to one customer's product taxonomy.
        Add projects/<id>/summary_fallback.json to customize; otherwise an
        empty, schema-agnostic default is used."""
        fallback_file = project_path / "summary_fallback.json"
        if fallback_file.exists():
            try:
                return json.loads(fallback_file.read_text(encoding="utf-8"))
            except Exception:
                logger.warning(f"Invalid summary_fallback.json at {fallback_file}, using empty default")
        return {
            "platforms": [],
            "critical_flows": [],
            "risk_areas": [],
            "features_per_platform": {},
        }

    def _generate_summary(self, content: str, project_id: str) -> Dict:
        """Use LLM once per project to create a compact summary."""
        llm = LLMClient()
        prompt = f"""Extract from the following project documentation a compact JSON summary with keys:
- "platforms": list of platform names
- "critical_flows": list of most important business flows
- "risk_areas": list of high-risk functionalities
- "features_per_platform": dict mapping platform name to list of key features

Document:
{content[:5000]}

Return only JSON.
"""
        response = llm.generate(prompt, temperature=0.2)
        try:
            cleaned = re.sub(r"```json\n?|```", "", response).strip()
            return json.loads(cleaned)
        except Exception:
            logger.warning(f"LLM summary failed for {project_id}, using fallback")
            return self._load_summary_fallback(self.projects_root / project_id)

    def _split_into_sections(self, content: str) -> List[Dict[str, str]]:
        sections = []
        lines = content.split("\n")
        current_heading = "Introduction"
        current_text = []
        for line in lines:
            if line.startswith("#") and len(line) > 1 and line[1] == " ":
                if current_text:
                    sections.append({"heading": current_heading, "text": "\n".join(current_text)})
                current_heading = line.strip("# ").strip()
                current_text = []
            else:
                current_text.append(line)
        if current_text:
            sections.append({"heading": current_heading, "text": "\n".join(current_text)})
        return sections

    def _build_embeddings(self, project_id: str, sections: List[Dict]) -> Optional[lancedb.DBConnection]:
        embedder = self._get_embedder()
        texts = [s["text"] for s in sections]
        if not texts:
            return None
        embeddings = embedder.encode(texts)
        df = pd.DataFrame({
            "id": [f"sec_{i}" for i in range(len(sections))],
            "heading": [s["heading"] for s in sections],
            "text": texts,
            "embedding": embeddings.tolist()
        })
        project_lance_path = self.projects_root / project_id / "embeddings.lance"
        project_lance_path.parent.mkdir(exist_ok=True)
        db = lancedb.connect(str(project_lance_path))
        db.create_table("sections", df, mode="overwrite")
        return db

    def _load_criticality_map(self, project_path: Path, content: str) -> Dict:
        """Per-project keyword -> {priority, severity} map, used to flag
        high-risk areas. Add projects/<id>/criticality.json to customize;
        otherwise empty (no product-specific assumptions baked into code)."""
        criticality_file = project_path / "criticality.json"
        if criticality_file.exists():
            return json.loads(criticality_file.read_text())
        return {}

    def get_project_summary(self, project_id: str) -> Optional[Dict]:
        if project_id not in self._projects_cache:
            if not self.load_project(project_id):
                return None
        return self._projects_cache[project_id]["summary"]

    def retrieve_relevant_context(self, project_id: str, query: str, top_k: int = 2) -> str:
        if project_id not in self._projects_cache:
            if not self.load_project(project_id):
                return ""
        embeddings_db = self._projects_cache[project_id]["embeddings"]
        if not embeddings_db:
            return ""
        embedder = self._get_embedder()
        query_emb = embedder.encode([query])[0]
        table = embeddings_db.open_table("sections")
        results = table.search(query_emb).limit(top_k).to_list()
        return "\n\n".join([r["text"][:500] for r in results])

    def infer_priority(self, project_id: str, test_name: str) -> Tuple[str, str]:
        if project_id not in self._projects_cache:
            return ("P2", "S3")
        criticality = self._projects_cache[project_id]["criticality"]
        test_lower = test_name.lower()
        for keyword, value in criticality.items():
            if keyword in test_lower:
                return (value["priority"], value["severity"])
        return ("P2", "S3")