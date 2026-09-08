from __future__ import annotations

import json
from typing import Any

import redis


class CrawlCursorStore:
    def __init__(self, redis_url: str) -> None:
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)

    def get(self, key: str) -> dict[str, Any]:
        raw = self._client.get(f"drivecheck:cursor:{key}")
        if not raw:
            return {}
        return json.loads(raw)

    def set(self, key: str, value: dict[str, Any]) -> None:
        self._client.set(f"drivecheck:cursor:{key}", json.dumps(value))
