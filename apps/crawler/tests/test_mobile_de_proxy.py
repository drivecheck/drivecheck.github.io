"""Mobile.de proxy wiring + WAF stop (no live network)."""

from __future__ import annotations

from drivecheck_crawler.adapters.mobile_de import (
    MobileDeAdapter,
    _redact_proxy,
    build_mobile_de_client,
)
from drivecheck_crawler.config import CrawlerConfig
from drivecheck_crawler.http_client import RateLimitedClient


class _Cursor:
    def __init__(self) -> None:
        self.store: dict = {"page": 1}

    def get(self, _key: str) -> dict:
        return dict(self.store)

    def set(self, _key: str, value: dict) -> None:
        self.store = dict(value)


class _FakeClient:
    proxy = "http://user:secret@proxy.example:8080"

    def __init__(self, responses: list[tuple[int, bytes]]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []
        self.delay_seconds = 0.0

    def request_raw(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> tuple[int, bytes]:
        self.calls.append(url)
        if not self._responses:
            raise AssertionError(f"unexpected request {method} {url}")
        return self._responses.pop(0)


def test_config_reads_mobile_de_http_proxy(monkeypatch):
    monkeypatch.setenv(
        "MOBILE_DE_HTTP_PROXY", "http://user:pass@127.0.0.1:8888"
    )
    monkeypatch.setenv("MOBILE_DE_USER_AGENT", "TestUA/1.0")
    cfg = CrawlerConfig()
    assert cfg.mobile_de_http_proxy == "http://user:pass@127.0.0.1:8888"
    assert cfg.mobile_de_user_agent == "TestUA/1.0"
    assert cfg.http_proxy_for("mobile_de") == "http://user:pass@127.0.0.1:8888"
    assert cfg.http_proxy_for("sauto") is None


def test_config_empty_proxy_is_none(monkeypatch):
    monkeypatch.setenv("MOBILE_DE_HTTP_PROXY", "")
    cfg = CrawlerConfig()
    assert cfg.mobile_de_http_proxy is None


def test_rate_limited_client_stores_proxy():
    cfg = CrawlerConfig()
    with RateLimitedClient(
        cfg, proxy="http://127.0.0.1:9999", delay_seconds=0
    ) as client:
        assert client.proxy == "http://127.0.0.1:9999"


def test_build_mobile_de_client_applies_proxy_and_de_headers():
    cfg = CrawlerConfig(
        mobile_de_http_proxy="http://proxy.example:8080",
        mobile_de_user_agent="ChromeTest/1",
    )
    with build_mobile_de_client(cfg, delay_seconds=0) as client:
        assert client.proxy == "http://proxy.example:8080"
        assert client._client.headers["User-Agent"] == "ChromeTest/1"
        assert "de-DE" in client._client.headers["Accept-Language"]


def test_redact_proxy_hides_password():
    assert (
        _redact_proxy("http://alice:s3cret@host:8080")
        == "http://alice:***@host:8080"
    )
    assert _redact_proxy("http://host:8080") == "http://host:8080"


def test_adapter_stops_on_403_waf_without_raising():
    """403 body must stop the batch (previously raise_for_status hid WAF)."""
    denied = b"<html><title>Zugriff verweigert / Access denied</title></html>"
    client = _FakeClient(
        [
            (200, b"<html>warmup</html>"),
            (403, denied),
        ]
    )
    adapter = MobileDeAdapter(
        client=client,  # type: ignore[arg-type]
        config=CrawlerConfig(),
        cursors=_Cursor(),  # type: ignore[arg-type]
    )
    rows = list(adapter.iter_listings(max_pages=3))
    assert rows == []
    # warmup + one search page, then stop (no page burn on WAF)
    assert len(client.calls) == 2
    assert "search.html" in client.calls[1]


def test_adapter_stops_on_access_denied_200_shell():
    """Some edges return 200 HTML shell with Access denied title."""
    denied = b"<html><title>Access denied</title>akamai denied</html>"
    client = _FakeClient(
        [
            (403, b"warmup denied"),
            (200, denied),
        ]
    )
    adapter = MobileDeAdapter(
        client=client,  # type: ignore[arg-type]
        config=CrawlerConfig(mobile_de_http_proxy="http://p:1@h:9"),
        cursors=_Cursor(),  # type: ignore[arg-type]
    )
    assert list(adapter.iter_listings(max_pages=2)) == []
    assert len(client.calls) == 2
