"""Redis Streams-based job queue.

Producer: XADD devmind:jobs
Consumer: XREADGROUP with consumer group devmind-workers
Dead-letter: messages that exceed MAX_RETRIES go to devmind:jobs:dead
"""
from __future__ import annotations

import json
import os
from typing import Any

import redis.asyncio as aioredis

STREAM_KEY = "devmind:jobs"
DEAD_LETTER_KEY = "devmind:jobs:dead"
GROUP_NAME = "devmind-workers"
MAX_RETRIES = 3


class JobQueue:
    def __init__(self, redis_url: str) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def setup(self) -> None:
        """Create consumer group if it doesn't exist."""
        try:
            await self._redis.xgroup_create(
                STREAM_KEY, GROUP_NAME, id="0", mkstream=True
            )
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def enqueue(self, job_id: str, pr_number: int, repo: str, **extra: Any) -> str:
        """Push a new review job onto the stream. Returns the stream entry ID."""
        payload = {
            "job_id": job_id,
            "pr_number": str(pr_number),
            "repo": repo,
            **{k: json.dumps(v) if not isinstance(v, str) else v for k, v in extra.items()},
        }
        entry_id = await self._redis.xadd(STREAM_KEY, payload)
        return entry_id

    async def consume(self, consumer_name: str, count: int = 1, block_ms: int = 2000):
        """Yield job payloads from the stream. Blocks up to block_ms if empty."""
        entries = await self._redis.xreadgroup(
            GROUP_NAME,
            consumer_name,
            {STREAM_KEY: ">"},
            count=count,
            block=block_ms,
        )
        if not entries:
            return []

        jobs = []
        for _stream, messages in entries:
            for entry_id, fields in messages:
                jobs.append((entry_id, fields))
        return jobs

    async def ack(self, entry_id: str) -> None:
        """Acknowledge successful processing of a message."""
        await self._redis.xack(STREAM_KEY, GROUP_NAME, entry_id)

    async def nack(self, entry_id: str, fields: dict[str, str]) -> None:
        """Handle failed message — move to dead-letter after MAX_RETRIES."""
        retries = int(fields.get("_retries", "0")) + 1
        if retries >= MAX_RETRIES:
            fields["_retries"] = str(retries)
            await self._redis.xadd(DEAD_LETTER_KEY, fields)
            await self._redis.xack(STREAM_KEY, GROUP_NAME, entry_id)
        else:
            # Re-enqueue with incremented retry count
            fields["_retries"] = str(retries)
            await self._redis.xadd(STREAM_KEY, fields)
            await self._redis.xack(STREAM_KEY, GROUP_NAME, entry_id)

    async def pending_count(self) -> int:
        info = await self._redis.xpending(STREAM_KEY, GROUP_NAME)
        return info.get("pending", 0) if isinstance(info, dict) else 0

    async def close(self) -> None:
        await self._redis.aclose()


_queue: JobQueue | None = None


def get_job_queue() -> JobQueue:
    global _queue
    if _queue is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _queue = JobQueue(url)
    return _queue
