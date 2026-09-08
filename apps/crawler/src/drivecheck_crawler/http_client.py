from __future__ import annotations

import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from drivecheck_crawler.config import CrawlerConfig


class RateLimitedClient:
    def __init__(
        self,
        config: CrawlerConfig,
        *,
        delay_seconds: float | None = None,
        proxy: str | None = None,
        headers: dict[str, str] | None = None,
        user_agent: str | None = None,
    ) -> None:
        self._config = config
        self._delay_seconds = (
            float(delay_seconds)
            if delay_seconds is not None
            else float(config.request_delay_seconds)
        )
        self._last_request_at = 0.0
        self.proxy = (proxy or "").strip() or None
        base_headers: dict[str, str] = {
            "User-Agent": user_agent or config.user_agent,
            "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
            "Accept-Language": "cs,en;q=0.8",
        }
        if headers:
            base_headers.update(headers)
        client_kwargs: dict[str, Any] = {
            "headers": base_headers,
            "timeout": config.http_timeout_seconds,
            "follow_redirects": True,
        }
        if self.proxy:
            client_kwargs["proxy"] = self.proxy
        self._client = httpx.Client(**client_kwargs)

    @property
    def delay_seconds(self) -> float:
        return self._delay_seconds

    def set_delay(self, delay_seconds: float) -> None:
        """Switch polite delay when rotating marketplace sources."""
        self._delay_seconds = max(0.0, float(delay_seconds))

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> RateLimitedClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        wait_for = self._delay_seconds - elapsed
        if wait_for > 0:
            time.sleep(wait_for)

    def request_raw(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, bytes]:
        """Throttle + fetch without raising on HTTP error statuses.

        Used by existence probe (404/410 must be readable).
        Transport/timeouts still raise (caller → UNCERTAIN).
        """
        self._throttle()
        response = self._client.request(
            method.upper(), url, params=params, headers=headers
        )
        self._last_request_at = time.monotonic()
        return response.status_code, response.content

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def get_json(self, url: str, *, params: dict[str, Any] | None = None, referer: str | None = None) -> Any:
        self._throttle()
        headers = {"Accept": "application/json"}
        if referer:
            headers["Referer"] = referer
        response = self._client.get(url, params=params, headers=headers)
        self._last_request_at = time.monotonic()
        if response.status_code in (429, 500, 502, 503, 504):
            response.raise_for_status()
        response.raise_for_status()
        return response.json()

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def get_text(self, url: str, *, referer: str | None = None) -> str:
        self._throttle()
        headers = {"Accept": "text/html,application/xhtml+xml"}
        if referer:
            headers["Referer"] = referer
        response = self._client.get(url, headers=headers)
        self._last_request_at = time.monotonic()
        if response.status_code in (429, 500, 502, 503, 504):
            response.raise_for_status()
        response.raise_for_status()
        return response.text

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def get_bytes(self, url: str, *, referer: str | None = None) -> bytes:
        self._throttle()
        headers = {"Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"}
        if referer:
            headers["Referer"] = referer
        response = self._client.get(url, headers=headers)
        self._last_request_at = time.monotonic()
        if response.status_code in (429, 500, 502, 503, 504):
            response.raise_for_status()
        response.raise_for_status()
        return response.content
