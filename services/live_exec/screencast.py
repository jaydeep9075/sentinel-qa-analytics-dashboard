"""Latest-frame cache for the optional live-browser view.

Deliberately not a durable database (see LIVE_EXECUTION_ARCHITECTURE.md #7.2):
frames arrive multiple times a second and are worthless the instant a newer
one arrives, so there is nothing to gain from writing them anywhere durable -
only the most recent frame per (run_id, worker_id) is ever kept.

Single-instance by default: a plain in-process dict is enough when there's
one backend process. Setting REDIS_URL (see services/config.py) switches
this to a Redis-backed cache instead, so multiple backend instances share
the same "latest frame per worker" state - a frame posted to instance A
becomes visible to a dashboard client streaming from instance B. This only
needs a shared latest-value store with expiry, not pub/sub like bus.py: the
data has no history worth fanning out, only a current value worth reading.

Functions are async so the Redis path (real network I/O) never blocks the
event loop; the in-memory path just doesn't happen to need to await anything.
"""

from __future__ import annotations

import logging
import time

from .. import config

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
except ImportError:  # redis is optional - see requirements.txt
    aioredis = None

# A frame nobody's refreshed in this long is stale/dead - expire it instead
# of leaking it forever if clear_run() is ever missed (process killed
# mid-run rather than finishing normally).
_FRAME_TTL_SECONDS = 15

_latest_frames: dict[tuple[str, int], tuple[float, str]] = {}
_redis = None

if config.REDIS_URL and aioredis is not None:
    _redis = aioredis.from_url(config.REDIS_URL, decode_responses=True)
elif config.REDIS_URL and aioredis is None:
    logger.warning(
        "REDIS_URL is set but the redis package isn't installed - the "
        "live-frame cache will only work correctly with a single backend "
        "instance. Run `pip install redis` to actually enable multi-instance mode."
    )


def _key(run_id: str, worker_id: int) -> str:
    return f"live_frame:{run_id}:{worker_id}"


async def set_frame(run_id: str, worker_id: int, frame_b64: str) -> None:
    if _redis is not None:
        await _redis.set(_key(run_id, worker_id), frame_b64, ex=_FRAME_TTL_SECONDS)
        return
    _latest_frames[(run_id, worker_id)] = (time.monotonic(), frame_b64)


async def get_frame(run_id: str, worker_id: int) -> str | None:
    if _redis is not None:
        return await _redis.get(_key(run_id, worker_id))
    entry = _latest_frames.get((run_id, worker_id))
    if entry is None:
        return None
    ts, frame_b64 = entry
    # Mirrors the Redis path's TTL: a process killed mid-run (skipping the
    # normal clear_run cleanup) would otherwise leak this entry forever.
    # Lazy expiry on read, not a sweep timer - same pattern as the other
    # in-process caches in this codebase (see _cache_get in main.py).
    if time.monotonic() - ts > _FRAME_TTL_SECONDS:
        _latest_frames.pop((run_id, worker_id), None)
        return None
    return frame_b64


async def clear_run(run_id: str, worker_count: int = 8) -> None:
    """worker_count bounds the Redis DELETE to keys that could plausibly
    exist (each frame key self-expires anyway via _FRAME_TTL_SECONDS, so
    missing a stray high worker index here just means it disappears a few
    seconds later on its own rather than instantly - not worth a SCAN)."""
    if _redis is not None:
        keys = [_key(run_id, w) for w in range(max(worker_count, 8))]
        try:
            await _redis.delete(*keys)
        except Exception:
            logger.warning("screencast: failed to clear redis frames for %s", run_id, exc_info=True)
        return
    for key in [k for k in _latest_frames if k[0] == run_id]:
        _latest_frames.pop(key, None)
