import logging
from pathlib import Path
from typing import Optional

from . import config

logger = logging.getLogger(__name__)

class RoleManager:
    def __init__(self, roles_root: Path = None):
        self.roles_root = roles_root or Path(config.ROLES_ROOT)
        self.roles_root.mkdir(exist_ok=True)
        self._roles_cache = {}

    def list_roles(self) -> list:
        return [f.stem for f in self.roles_root.glob("*.md")]

    def load_role(self, role_id: str) -> bool:
        role_file = self.roles_root / f"{role_id}.md"
        if not role_file.exists():
            logger.error(f"Role file {role_file} not found")
            return False
        self._roles_cache[role_id] = role_file.read_text(encoding="utf-8").strip()
        return True

    def get_role_instruction(self, role_id: str) -> Optional[str]:
        if role_id not in self._roles_cache:
            if not self.load_role(role_id):
                return None
        return self._roles_cache[role_id]