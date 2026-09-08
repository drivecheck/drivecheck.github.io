"""Mobile.de personal-car list discover (German import comps).

Spike (2026-08-06) + recheck (2026-08-07): Akamai returns hard
``Zugriff verweigert / Access denied`` (HTTP 403) from typical CZ and many
datacenter IPs — not a JS challenge. Browser-like headers / homepage warmup
alone do **not** unblock. Set ``MOBILE_DE_HTTP_PROXY`` to DE (or otherwise
unblocked) egress; the dedicated client uses DE Accept-Language + warmup.

When fetch succeeds, ``__NEXT_DATA__.props.pageProps.searchResults.items`` is
the list contract used by ``mobile_de_extract``. ``dam=0`` excludes damaged
inventory at search level; extract also skips Unfall/Bastler flags.

Cursor shape (Redis key ``mobile_de``)::

    {"page": int}

- 1-based ``pageNumber``
- wraps to 1 on empty / past maxPages
- Never mark_missing_removed from limited-page discover

Commercial fields only — EUR → CZK via fx.to_czk (nearest 100 CZK).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlencode

from drivecheck_crawler.adapters.base import SourceAdapter
from drivecheck_crawler.adapters.mobile_de_extract import (
    MOBILE_BASE,
    fields_from_record,
    list_records_from_html,
    parse_max_list_page,
)
from drivecheck_crawler.config import CrawlerConfig
from drivecheck_crawler.cursors import CrawlCursorStore
from drivecheck_crawler.http_client import RateLimitedClient
from drivecheck_crawler.models import ListingDTO
from drivecheck_crawler.normalize import now_utc

logger = logging.getLogger(__name__)

LIST_PATH = "/fahrzeuge/search.html"
WARMUP_URL = "https://www.mobile.de/"

# Polite browser-like defaults for the dedicated mobile_de client only.
# Does not change the shared DrivecheckBot client used by Sauto/Bazoš.
DEFAULT_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

_NAV_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-User": "?1",
}


def mobile_de_client_headers() -> dict[str, str]:
    return {
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": _NAV_HEADERS["Accept"],
    }


def build_mobile_de_client(
    config: CrawlerConfig,
    *,
    delay_seconds: float | None = None,
) -> RateLimitedClient:
    """Dedicated HTTP client for mobile_de (optional proxy + DE headers)."""
    if delay_seconds is not None:
        delay = float(delay_seconds)
    else:
        delay = float(
            config.delay_override_for("mobile_de") or config.request_delay_seconds
        )
    proxy = config.mobile_de_http_proxy
    ua = (config.mobile_de_user_agent or "").strip() or DEFAULT_BROWSER_UA
    if proxy:
        logger.info("Mobile.de HTTP client using proxy=%s", _redact_proxy(proxy))
    else:
        logger.warning(
            "Mobile.de HTTP client has no MOBILE_DE_HTTP_PROXY — "
            "Akamai usually returns 403 Access denied from CZ/DC IPs"
        )
    return RateLimitedClient(
        config,
        delay_seconds=delay,
        proxy=proxy,
        headers=mobile_de_client_headers(),
        user_agent=ua,
    )


def _redact_proxy(proxy: str) -> str:
    """Hide credentials in logs: scheme://user:***@host:port."""
    if "@" not in proxy:
        return proxy
    try:
        left, right = proxy.rsplit("@", 1)
        if "://" in left:
            scheme, rest = left.split("://", 1)
            user = rest.split(":", 1)[0] if rest else ""
            return f"{scheme}://{user}:***@{right}"
        return f"***@{right}"
    except Exception:
        return "(proxy set)"


def _is_waf_block(*, status: int, html: str) -> bool:
    if status in (403, 429):
        return True
    head = html[:4000]
    if "Access denied" in head or "Zugriff verweigert" in head:
        return True
    lowered = head.casefold()
    return "akamai" in lowered and "denied" in lowered


class MobileDeAdapter(SourceAdapter):
    source = "mobile_de"

    def __init__(
        self,
        client: RateLimitedClient,
        config: CrawlerConfig,
        cursors: CrawlCursorStore,
    ) -> None:
        self._client = client
        self._config = config
        self._cursors = cursors
        self._warmed = False

    def iter_listings(self, *, max_pages: int) -> Iterator[ListingDTO]:
        cursor = self._cursors.get("mobile_de")
        page = max(1, int(cursor.get("page", 1)))
        pages = 0
        self._warmup_session()

        while pages < max_pages:
            list_url = self._list_url(page)
            try:
                status, html = self._fetch_html(
                    list_url, referer=MOBILE_BASE + "/"
                )
            except Exception:
                logger.exception("Mobile.de list fetch failed page=%s", page)
                self._save_cursor(page=page)
                pages += 1
                page += 1
                continue

            if _is_waf_block(status=status, html=html):
                proxy_hint = (
                    "check MOBILE_DE_HTTP_PROXY egress"
                    if self._config.mobile_de_http_proxy
                    else "set MOBILE_DE_HTTP_PROXY to an unblocked (ideally DE) egress"
                )
                logger.warning(
                    "Mobile.de WAF/access denied status=%s page=%s — stopping batch "
                    "(%s; fixtures still cover extract)",
                    status,
                    page,
                    proxy_hint,
                )
                self._save_cursor(page=page)
                break

            if status >= 400:
                logger.warning(
                    "Mobile.de unexpected status=%s page=%s — stopping batch",
                    status,
                    page,
                )
                self._save_cursor(page=page)
                break

            records = list_records_from_html(html)
            max_page = parse_max_list_page(html)

            if not records:
                logger.info(
                    "Mobile.de empty list page=%s → wrap to 1 (max_page=%s)",
                    page,
                    max_page,
                )
                page = 1
                self._save_cursor(page=page)
                pages += 1
                continue

            for record in records:
                fields = fields_from_record(record)
                if fields is None:
                    continue
                yield self._fields_to_dto(fields)

            page += 1
            if max_page is not None and page > max_page:
                page = 1
            self._save_cursor(page=page)
            pages += 1

    def _warmup_session(self) -> None:
        """Hit homepage once so Akamai session cookies attach (helps via proxy)."""
        if self._warmed:
            return
        self._warmed = True
        try:
            status, _body = self._client.request_raw(
                "GET",
                WARMUP_URL,
                headers={
                    **_NAV_HEADERS,
                    "Sec-Fetch-Site": "none",
                    "Referer": "",
                },
            )
            logger.info("Mobile.de warmup status=%s url=%s", status, WARMUP_URL)
        except Exception:
            logger.debug("Mobile.de warmup failed", exc_info=True)

    def _fetch_html(self, url: str, *, referer: str) -> tuple[int, str]:
        status, content = self._client.request_raw(
            "GET",
            url,
            headers={**_NAV_HEADERS, "Referer": referer},
        )
        return status, content.decode("utf-8", errors="replace")

    @staticmethod
    def _list_url(page: int) -> str:
        # dam=0 → exclude damaged / accident inventory at search level
        qs = urlencode(
            {
                "dam": "0",
                "isSearchRequest": "true",
                "s": "Car",
                "vc": "Car",
                "ref": "srp",
                "pageNumber": str(max(1, page)),
            }
        )
        return f"{MOBILE_BASE}{LIST_PATH}?{qs}"

    def _save_cursor(self, *, page: int) -> None:
        self._cursors.set("mobile_de", {"page": page})

    def _fields_to_dto(self, fields: dict[str, Any]) -> ListingDTO:
        return ListingDTO(
            source="mobile_de",
            external_id=str(fields["external_id"]),
            url=str(fields["url"]),
            make=fields.get("make"),
            model=fields.get("model"),
            year=fields.get("year"),
            mileage_km=fields.get("mileage_km"),
            fuel=fields.get("fuel"),
            transmission=fields.get("transmission"),
            drive=fields.get("drive"),
            power_kw=fields.get("power_kw"),
            body=fields.get("body"),
            seller_type=fields.get("seller_type") or "unknown",
            region=fields.get("region"),
            price_czk=int(fields["price_czk"]),
            currency=str(fields.get("currency") or "EUR"),
            price_foreign=fields.get("price_foreign"),
            fx_rate_date=fields.get("fx_rate_date"),
            fx_czk_per_unit=fields.get("fx_czk_per_unit"),
            feature_keys=list(fields.get("feature_keys") or []),
            image_url=fields.get("image_url"),
            title=fields.get("title"),
            observed_at=now_utc(),
        )
