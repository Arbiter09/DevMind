"""Redis URL resolution for different deployment environments.

Priority order:
1. KV_URL            — Vercel KV (Upstash) — set automatically when you add Vercel KV
2. UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN — Upstash direct
3. REDIS_URL         — custom (local Docker, Railway private network, etc.)
4. Fallback          — redis://localhost:6379
"""
from __future__ import annotations

import os


def get_redis_url() -> str:
    # Vercel KV sets KV_URL as a redis:// connection string
    if url := os.getenv("KV_URL"):
        # Vercel KV URLs use rediss:// (TLS) — aioredis handles this natively
        return url

    # Upstash direct REST URL → convert to redis:// for aioredis compatibility
    upstash_url = os.getenv("UPSTASH_REDIS_REST_URL", "")
    upstash_token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
    if upstash_url and upstash_token:
        # Upstash also provides a redis:// URL via UPSTASH_REDIS_URL
        if redis_url := os.getenv("UPSTASH_REDIS_URL"):
            return redis_url

    # Standard Redis URL (local dev, Railway service, etc.)
    if url := os.getenv("REDIS_URL"):
        return url

    return "redis://localhost:6379"
