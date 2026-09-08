"""AutoScout24.de personal-car list discover (German market / import comps).

Spike note (2026-08-06): ``www.autoscout24.de/lst`` returns SSR ``__NEXT_DATA__``
with rich listing cards at polite delay. Prefer DE host (cy=D) — CZ dealers
importing from DE/AT typically use this inventory. ``damaged_listing=exclude``
plus extract-time accident skip.

Cursor shape (Redis key ``autoscout24``)::

    {"page": int}

- page is 1-based AS24 ``page=`` query
- wraps to 1 when empty or past numberOfPages (capped at 200)
- Never call mark_missing_removed from limited-page discover

Commercial fields only — never phone / email / street / seller name / VIN.
EUR → CZK via fx.to_czk (nearest 100 CZK).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlencode

from drivecheck_crawler.adapters.autoscout24_extract import (
    AS24_BASE,
    fields_from_record,
    list_records_from_html,
    parse_max_list_page,
)
from drivecheck_crawler.adapters.base import SourceAdapter
from drivecheck_crawler.config import CrawlerConfig
from drivecheck_crawler.cursors import CrawlCursorStore
from drivecheck_crawler.http_client import RateLimitedClient
from drivecheck_crawler.models import ListingDTO
from drivecheck_crawler.normalize import now_utc

logger = logging.getLogger(__name__)

LIST_PATH = "/lst"


class Autoscout24Adapter(SourceAdapter):
    source = "autoscout24"

    def __init__(
        self,
        client: RateLimitedClient,
        config: CrawlerConfig,
        cursors: CrawlCursorStore,
    ) -> None:
        self._client = client
        self._config = config
        self._cursors = cursors

    def iter_listings(self, *, max_pages: int) -> Iterator[ListingDTO]:
        cursor = self._cursors.get("autoscout24")
        page = max(1, int(cursor.get("page", 1)))
        pages = 0

        while pages < max_pages:
            list_url = self._list_url(page)
            try:
                html = self._client.get_text(list_url, referer=AS24_BASE + "/")
            except Exception:
                logger.exception("AutoScout24 list fetch failed page=%s", page)
                self._save_cursor(page=page)
                pages += 1
                page += 1
                continue

            if "Access denied" in html[:2000] or "Zugriff verweigert" in html[:2000]:
                logger.warning(
                    "AutoScout24 WAF/access denied page=%s — stopping batch", page
                )
                self._save_cursor(page=page)
                break

            records = list_records_from_html(html)
            max_page = parse_max_list_page(html)

            if not records:
                logger.info(
                    "AutoScout24 empty list page=%s → wrap to 1 (max_page=%s)",
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

    @staticmethod
    def _list_url(page: int) -> str:
        # damaged_listing=exclude — product: no Unfallwagen in default discover
        qs = urlencode(
            {
                "atype": "C",
                "cy": "D",
                "damaged_listing": "exclude",
                "desc": "0",
                "sortage": "age",
                "ustate": "N,U",
                "page": str(max(1, page)),
            }
        )
        return f"{AS24_BASE}{LIST_PATH}?{qs}"

    def _save_cursor(self, *, page: int) -> None:
        self._cursors.set("autoscout24", {"page": page})

    def _fields_to_dto(self, fields: dict[str, Any]) -> ListingDTO:
        return ListingDTO(
            source="autoscout24",
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
            displacement_cc=fields.get("displacement_cc"),
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
