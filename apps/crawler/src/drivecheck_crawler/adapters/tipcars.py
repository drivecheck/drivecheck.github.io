"""TipCars osobní list + optional detail enrich.

Cursor shape (Redis key ``tipcars``)::

    {"page": int, "page_size": int}

- ``page`` is 1-based TipCars ``str={page}-{page_size}`` index
- page 1 uses bare ``/osobni`` (no query); page ≥2 uses ``?str=N-20``
- after each list page cursor advances; wraps to 1 when empty or past max
- no offset wall like Sauto (~10k); TipCars paginates to ~thousands of pages
- ``TIPCARS_FETCH_DETAILS`` defaults false (list JSON-LD for discover speed);
  when true, detail HTML is fetched only if year/km/fuel are missing

Commercial fields only — never phone / email / street / seller name / VIN (productID).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from drivecheck_crawler.adapters.base import SourceAdapter
from drivecheck_crawler.adapters.tipcars_extract import (
    fields_from_product,
    find_product,
    list_products_from_html,
    merge_field_dicts,
    parse_json_ld_blocks,
    parse_max_list_page,
)
from drivecheck_crawler.config import CrawlerConfig
from drivecheck_crawler.cursors import CrawlCursorStore
from drivecheck_crawler.http_client import RateLimitedClient
from drivecheck_crawler.models import ListingDTO
from drivecheck_crawler.normalize import extract_features_from_text, now_utc, strip_contact_text

logger = logging.getLogger(__name__)

TIPCARS_BASE = "https://www.tipcars.com"
TIPCARS_LIST = f"{TIPCARS_BASE}/osobni"


def _needs_detail_enrich(dto: ListingDTO) -> bool:
    """Skip HTML detail when list JSON already has core pricing comps fields."""
    return dto.year is None or dto.mileage_km is None or dto.fuel is None


class TipCarsAdapter(SourceAdapter):
    source = "tipcars"

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
        cursor = self._cursors.get("tipcars")
        page_size = int(
            cursor.get("page_size") or self._config.tipcars_page_size or 20
        )
        page = max(1, int(cursor.get("page", 1)))
        pages = 0

        while pages < max_pages:
            list_url = self._list_url(page, page_size)
            try:
                html = self._client.get_text(list_url, referer=TIPCARS_BASE + "/")
            except Exception:
                logger.exception("TipCars list fetch failed page=%s", page)
                self._save_cursor(page=page, page_size=page_size)
                pages += 1
                page += 1
                continue

            products = list_products_from_html(html)
            max_page = parse_max_list_page(html, page_size=page_size)

            if not products:
                logger.info(
                    "TipCars empty list page=%s → wrap to 1 (max_page=%s)",
                    page,
                    max_page,
                )
                page = 1
                self._save_cursor(page=page, page_size=page_size)
                pages += 1
                continue

            for product in products:
                dto = self._product_to_dto(product)
                if dto is None:
                    continue
                if self._config.tipcars_fetch_details and _needs_detail_enrich(dto):
                    dto = self._enrich_from_detail(dto)
                yield dto

            page += 1
            if max_page is not None and page > max_page:
                page = 1
            self._save_cursor(page=page, page_size=page_size)
            pages += 1

    @staticmethod
    def _list_url(page: int, page_size: int) -> str:
        if page <= 1:
            return TIPCARS_LIST
        return f"{TIPCARS_LIST}?str={page}-{page_size}"

    def _save_cursor(self, *, page: int, page_size: int) -> None:
        self._cursors.set(
            "tipcars",
            {"page": page, "page_size": page_size},
        )

    def _product_to_dto(self, product: dict[str, Any]) -> ListingDTO | None:
        fields = fields_from_product(product)
        if fields is None:
            return None
        return self._fields_to_dto(fields)

    def _fields_to_dto(self, fields: dict[str, Any]) -> ListingDTO:
        url = fields.get("url")
        if not url:
            raise ValueError("TipCars listing requires url (list discovery)")
        title_raw = fields.get("title")
        title = strip_contact_text(title_raw) if isinstance(title_raw, str) else None
        feature_keys = extract_features_from_text(title or "")
        return ListingDTO(
            source="tipcars",
            external_id=str(fields["external_id"]),
            url=str(url),
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
            feature_keys=feature_keys,
            image_url=fields.get("image_url"),
            title=title,
            observed_at=now_utc(),
        )

    def _enrich_from_detail(self, base: ListingDTO) -> ListingDTO:
        try:
            html = self._client.get_text(base.url, referer=TIPCARS_LIST)
        except Exception:
            logger.debug(
                "TipCars detail fetch failed id=%s", base.external_id, exc_info=True
            )
            return base

        product = find_product(parse_json_ld_blocks(html))
        if not product:
            return base

        enrich = fields_from_product(product)
        if enrich is None:
            return base

        base_fields = {
            "external_id": base.external_id,
            "url": base.url,
            "make": base.make,
            "model": base.model,
            "year": base.year,
            "mileage_km": base.mileage_km,
            "fuel": base.fuel,
            "transmission": base.transmission,
            "drive": base.drive,
            "power_kw": base.power_kw,
            "displacement_cc": base.displacement_cc,
            "body": base.body,
            "seller_type": base.seller_type,
            "region": base.region,
            "price_czk": base.price_czk,
            "image_url": base.image_url,
            "title": base.title,
        }
        merged = merge_field_dicts(base_fields, enrich)
        # Keep stable id/url from list discovery.
        merged["external_id"] = base.external_id
        merged["url"] = base.url
        dto = self._fields_to_dto(merged)
        return dto.model_copy(update={"observed_at": now_utc()})
