"""Redis cache-aside layer for MCP tool results.

Cache key structure: mcp:{tool_name}:{sha}:{path_or_pr_hash}

TTL policy:
  read_file        → 86400s  (content at a git SHA is immutable)
  get_pr_diff      → 3600s   (diff is stable at a given HEAD SHA)
  get_pr_metadata  → 300s    (labels/status can change)
  list_changed_files → 3600s
  get_file_history → 1800s
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import redis.asyncio as aioredis

# Per-tool TTL in seconds
TOOL_TTL: dict[str, int] = {
    "read_file": 86400,
    "get_pr_diff": 3600,
    "get_pr_metadata": 300,
    "list_changed_files": 3600,
    "get_file_history": 1800,
}

DEFAULT_TTL = 600


def _build_key(tool_name: str, **kwargs: Any) -> str:
    """Build a deterministic cache key from tool name and arguments."""
    stable = json.dumps(kwargs, sort_keys=True)
    digest = hashlib.sha256(stable.encode()).hexdigest()[:16]
    return f"mcp:{tool_name}:{digest}"


class CacheClient:
    def __init__(self, redis_url: str) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._hits = 0
        self._misses = 0

    async def get(self, tool_name: str, **kwargs: Any) -> tuple[Any | None, bool]:
        """Return (value, was_hit). Value is None on miss."""
        key = _build_key(tool_name, **kwargs)
        raw = await self._redis.get(key)
        if raw is not None:
            self._hits += 1
            return json.loads(raw), True
        self._misses += 1
        return None, False

    async def set(self, tool_name: str, value: Any, **kwargs: Any) -> None:
        """Store a tool result with the appropriate TTL."""
        key = _build_key(tool_name, **kwargs)
        ttl = TOOL_TTL.get(tool_name, DEFAULT_TTL)
        await self._redis.setex(key, ttl, json.dumps(value))

    @property
    def hit_count(self) -> int:
        return self._hits

    @property
    def miss_count(self) -> int:
        return self._misses

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    async def flush_stats(self) -> dict[str, Any]:
        stats = {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
        }
        self._hits = 0
        self._misses = 0
        return stats

    async def close(self) -> None:
        await self._redis.aclose()


_client: CacheClient | None = None


def get_cache_client() -> CacheClient:
    global _client
    if _client is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _client = CacheClient(url)
    return _client
