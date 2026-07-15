import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from . import config

_LOCK = threading.Lock()
_STORE_PATH = Path(config.DATA_BASE_PATH) / "token_usage_store.json"


def _norm_user(user_id: str | None) -> str:
    return str(user_id or "").strip().lower() or "anonymous"


def _norm_workspace(workspace_id: str | None) -> str:
    return str(workspace_id or "").strip().lower() or str(getattr(config, "DEFAULT_WORKSPACE_ID", "default") or "default").strip().lower()


def _empty_totals() -> Dict[str, int]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "calls": 0,
    }


def _load_store() -> Dict:
    if not _STORE_PATH.exists():
        return {"users": {}, "updated_at": ""}
    try:
        return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"users": {}, "updated_at": ""}


def _save_store(data: Dict) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    _STORE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def record_usage(
    user_id: str | None,
    workspace_id: str | None,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
) -> None:
    uid = _norm_user(user_id)
    wid = _norm_workspace(workspace_id)
    model_key = str(model or "unknown").strip() or "unknown"

    with _LOCK:
        store = _load_store()
        users = store.setdefault("users", {})
        user_key = f"{wid}:{uid}"
        user_obj = users.setdefault(user_key, {
            "workspace_id": wid,
            "user_id": uid,
            "totals": _empty_totals(),
            "by_model": {},
        })

        totals = user_obj.setdefault("totals", _empty_totals())
        totals["prompt_tokens"] = int(totals.get("prompt_tokens", 0)) + int(prompt_tokens or 0)
        totals["completion_tokens"] = int(totals.get("completion_tokens", 0)) + int(completion_tokens or 0)
        totals["total_tokens"] = int(totals.get("total_tokens", 0)) + int(total_tokens or 0)
        totals["calls"] = int(totals.get("calls", 0)) + 1

        by_model = user_obj.setdefault("by_model", {})
        model_totals = by_model.setdefault(model_key, _empty_totals())
        model_totals["prompt_tokens"] = int(model_totals.get("prompt_tokens", 0)) + int(prompt_tokens or 0)
        model_totals["completion_tokens"] = int(model_totals.get("completion_tokens", 0)) + int(completion_tokens or 0)
        model_totals["total_tokens"] = int(model_totals.get("total_tokens", 0)) + int(total_tokens or 0)
        model_totals["calls"] = int(model_totals.get("calls", 0)) + 1

        _save_store(store)


def get_usage(user_id: str | None, workspace_id: str | None) -> Dict:
    uid = _norm_user(user_id)
    wid = _norm_workspace(workspace_id)
    user_key = f"{wid}:{uid}"

    with _LOCK:
        store = _load_store()
        user_obj = store.get("users", {}).get(user_key, None)
        if not user_obj:
            return {"totals": _empty_totals(), "by_model": {}, "scope": {"workspace_id": wid, "user_id": uid}}
        return {
            "totals": user_obj.get("totals", _empty_totals()),
            "by_model": user_obj.get("by_model", {}),
            "scope": {"workspace_id": wid, "user_id": uid},
            "updated_at": store.get("updated_at", ""),
        }
