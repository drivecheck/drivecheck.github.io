from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import redis


class CrawlHealthStore:
    def __init__(self, redis_url: str) -> None:
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)

    def record_batch(self, source: str, *, ingested: int, errors: int) -> None:
        payload = {
            "source": source,
            "ingested": ingested,
            "errors": errors,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self._client.set(f"drivecheck:health:{source}", json.dumps(payload))
        self._client.set(
            "drivecheck:health:crawler",
            json.dumps(
                {
                    "last_source": source,
                    "at": payload["at"],
                    "ingested": ingested,
                    "errors": errors,
                }
            ),
        )

    def get(self, source: str) -> dict[str, Any]:
        raw = self._client.get(f"drivecheck:health:{source}")
        if not raw:
            return {}
        return json.loads(raw)

    def get_all(self) -> dict[str, Any]:
        crawler_raw = self._client.get("drivecheck:health:crawler")
        return {
            "sauto": self.get("sauto"),
            "bazos": self.get("bazos"),
            "crawler": json.loads(crawler_raw) if crawler_raw else {},
        }
