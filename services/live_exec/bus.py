"""In-process pub/sub used to push live-run updates to connected SSE clients.

Single-instance by default: an in-memory asyncio.Queue per subscriber costs
nothing and is instant, and that's all that's needed as long as there's
exactly one backend process. The moment Sentinel runs as more than one
backend instance behind a load balancer, this breaks silently - a reporter's
POST and a dashboard's SSE connection can land on different instances, and
the in-memory queue on instance A is invisible to instance B, so that viewer
just never sees updates.

Setting REDIS_URL (see services/config.py) switches this on transparently:
every publish goes out over a Redis pub/sub channel instead of straight into
local queues, and every subscribe listens on that same channel - so it works
correctly across any number of instances without router.py, the reporter, or
the frontend needing to know or care which mode is active.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict

from .. import config

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
except ImportError:  # redis is optional - see requirements.txt
    aioredis = None


class RunBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._redis = None
        # One Redis subscription per run_id per instance (not one per
        # dashboard client) - whatever it receives gets fanned out to every
        # local queue for that run, same as a same-instance publish() would.
        self._listen_tasks: dict[str, asyncio.Task] = {}

        if config.REDIS_URL and aioredis is not None:
            self._redis = aioredis.from_url(config.REDIS_URL, decode_responses=True)
            logger.info("live-execution bus: multi-instance mode via Redis")
        elif config.REDIS_URL and aioredis is None:
            logger.warning(
                "REDIS_URL is set but the redis package isn't installed - "
                "falling back to single-instance in-memory pub/sub. "
                "Run `pip install redis` to actually enable multi-instance mode."
            )

    def subscribe(self, run_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers[run_id].add(queue)
        if self._redis is not None and run_id not in self._listen_tasks:
            self._listen_tasks[run_id] = asyncio.create_task(self._listen(run_id))
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(run_id)
        if not subs:
            return
        subs.discard(queue)
        if not subs:
            self._subscribers.pop(run_id, None)
            task = self._listen_tasks.pop(run_id, None)
            if task:
                task.cancel()

    def publish(self, run_id: str, message: dict) -> None:
        """Fire-and-forget, same contract as before: callers don't await
        this. In Redis mode, everything (including this instance's own
        subscribers) is delivered via the _listen loop below, so this only
        publishes remotely - not also directly into local queues - to avoid
        delivering the same message to a same-instance viewer twice."""
        if self._redis is not None:
            asyncio.create_task(self._publish_remote(run_id, message))
            return
        for queue in list(self._subscribers.get(run_id, ())):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # A slow/stalled subscriber shouldn't back-pressure ingestion.
                pass

    async def _publish_remote(self, run_id: str, message: dict) -> None:
        try:
            await self._redis.publish(f"live:{run_id}", json.dumps(message, default=str))
        except Exception:
            logger.warning("bus: failed to publish to redis for %s", run_id, exc_info=True)

    async def _listen(self, run_id: str) -> None:
        assert self._redis is not None
        pubsub = self._redis.pubsub()
        channel = f"live:{run_id}"
        try:
            await pubsub.subscribe(channel)
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                try:
                    payload = json.loads(msg["data"])
                except (TypeError, ValueError):
                    continue
                for queue in list(self._subscribers.get(run_id, ())):
                    try:
                        queue.put_nowait(payload)
                    except asyncio.QueueFull:
                        pass
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.warning("bus: redis listen loop failed for %s", run_id, exc_info=True)
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception:
                pass


bus = RunBus()
