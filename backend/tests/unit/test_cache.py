"""Unit tests for the Redis cache-aside layer."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cache.redis_cache import TOOL_TTL, CacheClient, _build_key


class TestBuildKey:
    def test_same_args_produce_same_key(self):
        k1 = _build_key("read_file", path="foo.py", repo="owner/repo", ref="abc123")
        k2 = _build_key("read_file", path="foo.py", repo="owner/repo", ref="abc123")
        assert k1 == k2

    def test_different_args_produce_different_keys(self):
        k1 = _build_key("read_file", path="foo.py", repo="owner/repo", ref="abc123")
        k2 = _build_key("read_file", path="bar.py", repo="owner/repo", ref="abc123")
        assert k1 != k2

    def test_key_includes_tool_name(self):
        k = _build_key("get_pr_diff", pr_number=42, repo="owner/repo")
        assert k.startswith("mcp:get_pr_diff:")

    def test_arg_order_does_not_matter(self):
        k1 = _build_key("read_file", path="a.py", ref="sha1", repo="r/r")
        k2 = _build_key("read_file", repo="r/r", path="a.py", ref="sha1")
        assert k1 == k2


class TestToolTTL:
    def test_read_file_has_longest_ttl(self):
        assert TOOL_TTL["read_file"] >= max(
            v for k, v in TOOL_TTL.items() if k != "read_file"
        )

    def test_get_pr_metadata_has_shortest_ttl(self):
        assert TOOL_TTL["get_pr_metadata"] <= min(
            v for k, v in TOOL_TTL.items() if k != "get_pr_metadata"
        )

    def test_all_expected_tools_have_ttl(self):
        required = {"read_file", "get_pr_diff", "get_pr_metadata", "list_changed_files"}
        assert required.issubset(TOOL_TTL.keys())


class TestCacheClient:
    def _make_client(self) -> tuple[CacheClient, MagicMock]:
        client = CacheClient.__new__(CacheClient)
        client._hits = 0
        client._misses = 0
        mock_redis = AsyncMock()
        client._redis = mock_redis
        return client, mock_redis

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self):
        client, mock_redis = self._make_client()
        mock_redis.get.return_value = None

        value, hit = await client.get("read_file", path="a.py", repo="r/r", ref="sha")
        assert value is None
        assert hit is False
        assert client.miss_count == 1
        assert client.hit_count == 0

    @pytest.mark.asyncio
    async def test_cache_hit_returns_value(self):
        client, mock_redis = self._make_client()
        mock_redis.get.return_value = json.dumps({"content": "file contents"})

        value, hit = await client.get("read_file", path="a.py", repo="r/r", ref="sha")
        assert value == {"content": "file contents"}
        assert hit is True
        assert client.hit_count == 1
        assert client.miss_count == 0

    @pytest.mark.asyncio
    async def test_set_uses_correct_ttl(self):
        client, mock_redis = self._make_client()

        await client.set("read_file", "file content", path="a.py", repo="r/r", ref="sha")
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        # Second positional arg is TTL
        ttl_used = call_args[0][1]
        assert ttl_used == TOOL_TTL["read_file"]

    @pytest.mark.asyncio
    async def test_set_serialises_value_as_json(self):
        client, mock_redis = self._make_client()
        value = {"files": ["a.py", "b.py"], "count": 2}

        await client.set("list_changed_files", value, pr_number=1, repo="r/r")
        call_args = mock_redis.setex.call_args[0]
        stored = json.loads(call_args[2])
        assert stored == value

    @pytest.mark.asyncio
    async def test_hit_rate_calculation(self):
        client, mock_redis = self._make_client()
        mock_redis.get.side_effect = [
            json.dumps("v1"),  # hit
            json.dumps("v2"),  # hit
            None,              # miss
            None,              # miss
        ]

        for _ in range(4):
            await client.get("get_pr_diff", pr_number=1, repo="r/r")

        assert client.hit_rate == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_flush_stats_resets_counters(self):
        client, mock_redis = self._make_client()
        client._hits = 10
        client._misses = 5

        stats = await client.flush_stats()
        assert stats["hits"] == 10
        assert stats["misses"] == 5
        assert client._hits == 0
        assert client._misses == 0
