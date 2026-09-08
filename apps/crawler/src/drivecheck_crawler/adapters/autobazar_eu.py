"""Autobazar.eu CZ osobní list (+ optional detail enrich).

CZ vs SK policy
---------------
Default discover uses ``location=200000000`` (Česká republika) and drops any
SK row that still appears. SK inventory is out of scope for Phase A2 comps.

Cursor shape (Redis key ``autobazar_eu``)::

    {
      "brand_idx": int,
      "page": int,
      "price_from": int | null,   # EUR inclusive, optional band
      "price_to": int | null      # EUR inclusive, optional band
    }

- List URL: ``/cs/vysledky/osobne-vozidla/{brand}/?location=200000000&page=N``
- Portal caps ``maxPage`` at 50 (~20/page ⇒ ~1000/query). Brands larger than
  that (Škoda/VW/…) rotate through EUR price bands so we don't stall on page 50.
- After empty page / past maxPage, advance brand (and price band when used).
- Never call mark_missing_removed from limited-page discover.

Commercial fields only — never phone / email / street / seller name / VIN.
Offers are usually EUR (€); FX → ``price_czk`` via ``to_czk`` (nearest 100).
When the portal already exposes a CZK mirror (``unitPrice == 1``), store that
native CZK amount without EUR×rate — see ``autobazar_eu_extract.offer_price_amount``.
``AUTOBAZAR_EU_FETCH_DETAILS`` defaults false (list already has year/km/fuel);
when true, detail is fetched only if those fields are missing.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlencode

from drivecheck_crawler.adapters.autobazar_eu_extract import (
    AUTOBAZAR_BASE,
    CZ_LOCATION_ID,
    detail_record_from_html,
    fields_from_record,
    list_records_from_html,
    merge_field_dicts,
    parse_max_list_page,
)
from drivecheck_crawler.adapters.base import SourceAdapter
from drivecheck_crawler.config import CrawlerConfig
from drivecheck_crawler.cursors import CrawlCursorStore
from drivecheck_crawler.http_client import RateLimitedClient
from drivecheck_crawler.models import ListingDTO
from drivecheck_crawler.normalize import extract_features_from_text, now_utc, strip_contact_text

logger = logging.getLogger(__name__)

LIST_PATH = "/cs/vysledky/osobne-vozidla"

# Personal-car brand SEF paths (CZ-relevant). Rotated to stay under maxPage=50.
AUTOBAZAR_BRANDS = [
    "skoda",
    "volkswagen",
    "mercedes-benz",
    "ford",
    "hyundai",
    "bmw",
    "volvo",
    "peugeot",
    "opel",
    "renault",
    "audi",
    "kia",
    "citroen",
    "toyota",
    "dacia",
    "land-rover",
    "seat",
    "nissan",
    "mazda",
    "suzuki",
    "mitsubishi",
    "fiat",
    "jeep",
    "tesla",
    "honda",
    "alfa-romeo",
    "cupra",
    "mini",
    "porsche",
]

# EUR edges for brands that exceed the ~1000-row page wall.
PRICE_EDGES_EUR: list[int | None] = [
    0,
    5_000,
    10_000,
    15_000,
    20_000,
    25_000,
    30_000,
    40_000,
    50_000,
    70_000,
    100_000,
    None,
]

# Brands known to exceed maxPage*page_size under CZ filter alone.
_LARGE_BRANDS = frozenset({"skoda", "volkswagen", "mercedes-benz", "ford", "bmw", "hyundai"})


def _needs_detail_enrich(dto: ListingDTO) -> bool:
    """Skip detail when list __NEXT_DATA__ already has core comps fields."""
    return dto.year is None or dto.mileage_km is None or dto.fuel is None


class AutobazarEuAdapter(SourceAdapter):
    source = "autobazar_eu"

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
        cursor = self._cursors.get("autobazar_eu")
        brand_idx = int(cursor.get("brand_idx", 0)) % len(AUTOBAZAR_BRANDS)
        page = max(1, int(cursor.get("page", 1)))
        price_from = self._optional_int(cursor.get("price_from"))
        price_to = self._optional_int(cursor.get("price_to"))
        pages = 0

        while pages < max_pages:
            brand = AUTOBAZAR_BRANDS[brand_idx]
            if brand in _LARGE_BRANDS and price_from is None and price_to is None:
                price_from, price_to = self._first_price_band()

            list_url = self._list_url(
                brand=brand,
                page=page,
                price_from=price_from,
                price_to=price_to,
            )
            try:
                html = self._client.get_text(
                    list_url, referer=f"{AUTOBAZAR_BASE}/cs/"
                )
            except Exception:
                logger.exception(
                    "Autobazar.eu list fetch failed brand=%s page=%s", brand, page
                )
                self._save_cursor(
                    brand_idx=brand_idx,
                    page=page,
                    price_from=price_from,
                    price_to=price_to,
                )
                pages += 1
                page += 1
                continue

            records = list_records_from_html(html)
            max_page = parse_max_list_page(html) or 50

            if not records:
                logger.info(
                    "Autobazar.eu empty list brand=%s page=%s band=%s-%s → advance",
                    brand,
                    page,
                    price_from,
                    price_to,
                )
                brand_idx, page, price_from, price_to = self._advance_slice(
                    brand_idx=brand_idx,
                    price_from=price_from,
                    price_to=price_to,
                )
                self._save_cursor(
                    brand_idx=brand_idx,
                    page=page,
                    price_from=price_from,
                    price_to=price_to,
                )
                pages += 1
                continue

            for record in records:
                dto = self._record_to_dto(record)
                if dto is None:
                    continue
                if self._config.autobazar_eu_fetch_details and _needs_detail_enrich(
                    dto
                ):
                    dto = self._enrich_from_detail(dto)
                yield dto

            page += 1
            if page > max_page:
                brand_idx, page, price_from, price_to = self._advance_slice(
                    brand_idx=brand_idx,
                    price_from=price_from,
                    price_to=price_to,
                )
            self._save_cursor(
                brand_idx=brand_idx,
                page=page,
                price_from=price_from,
                price_to=price_to,
            )
            pages += 1

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _first_price_band() -> tuple[int | None, int | None]:
        return PRICE_EDGES_EUR[0], (
            None
            if PRICE_EDGES_EUR[1] is None
            else int(PRICE_EDGES_EUR[1]) - 1
        )

    def _advance_slice(
        self,
        *,
        brand_idx: int,
        price_from: int | None,
        price_to: int | None,
    ) -> tuple[int, int, int | None, int | None]:
        brand = AUTOBAZAR_BRANDS[brand_idx]
        if brand in _LARGE_BRANDS:
            next_band = self._next_price_band(price_from, price_to)
            if next_band is not None:
                return brand_idx, 1, next_band[0], next_band[1]
        next_brand = (brand_idx + 1) % len(AUTOBAZAR_BRANDS)
        next_from: int | None = None
        next_to: int | None = None
        if AUTOBAZAR_BRANDS[next_brand] in _LARGE_BRANDS:
            next_from, next_to = self._first_price_band()
        return next_brand, 1, next_from, next_to

    @staticmethod
    def _next_price_band(
        price_from: int | None, price_to: int | None
    ) -> tuple[int | None, int | None] | None:
        # Find current band index by matching edges.
        edges = PRICE_EDGES_EUR
        cur_from = 0 if price_from is None else int(price_from)
        for idx in range(len(edges) - 1):
            band_from = int(edges[idx] or 0)
            next_edge = edges[idx + 1]
            band_to = None if next_edge is None else int(next_edge) - 1
            if band_from == cur_from and band_to == (
                None if price_to is None else int(price_to)
            ):
                nxt = idx + 1
                if nxt >= len(edges) - 1:
                    return None
                nf = int(edges[nxt] or 0)
                ne = edges[nxt + 1]
                nt = None if ne is None else int(ne) - 1
                return nf, nt
        # Unknown band → start next edge after current from.
        for idx in range(len(edges) - 1):
            if int(edges[idx] or 0) > cur_from:
                nf = int(edges[idx] or 0)
                ne = edges[idx + 1]
                nt = None if ne is None else int(ne) - 1
                return nf, nt
        return None

    def _list_url(
        self,
        *,
        brand: str,
        page: int,
        price_from: int | None,
        price_to: int | None,
    ) -> str:
        base = f"{AUTOBAZAR_BASE}{LIST_PATH}/{brand}/"
        params: dict[str, str | int] = {"location": CZ_LOCATION_ID}
        if page > 1:
            params["page"] = page
        if price_from is not None:
            params["priceFrom"] = int(price_from)
        if price_to is not None:
            params["priceTo"] = int(price_to)
        return f"{base}?{urlencode(params)}"

    def _save_cursor(
        self,
        *,
        brand_idx: int,
        page: int,
        price_from: int | None,
        price_to: int | None,
    ) -> None:
        self._cursors.set(
            "autobazar_eu",
            {
                "brand_idx": brand_idx,
                "page": page,
                "price_from": price_from,
                "price_to": price_to,
            },
        )

    def _record_to_dto(self, record: dict[str, Any]) -> ListingDTO | None:
        fields = fields_from_record(record, require_czech=True)
        if fields is None:
            return None
        return self._fields_to_dto(fields)

    def _fields_to_dto(self, fields: dict[str, Any]) -> ListingDTO:
        url = fields.get("url")
        if not url:
            raise ValueError("Autobazar.eu listing requires url")
        title_raw = fields.get("title")
        title = strip_contact_text(title_raw) if isinstance(title_raw, str) else None
        feature_keys = extract_features_from_text(title or "")
        return ListingDTO(
            source="autobazar_eu",
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
            currency=str(fields.get("currency") or "EUR"),
            price_foreign=fields.get("price_foreign"),
            fx_rate_date=fields.get("fx_rate_date"),
            fx_czk_per_unit=fields.get("fx_czk_per_unit"),
            feature_keys=feature_keys,
            image_url=fields.get("image_url"),
            title=title,
            published_at=fields.get("published_at"),
            observed_at=now_utc(),
        )

    def _enrich_from_detail(self, base: ListingDTO) -> ListingDTO:
        try:
            html = self._client.get_text(
                base.url, referer=f"{AUTOBAZAR_BASE}{LIST_PATH}/"
            )
        except Exception:
            logger.debug(
                "Autobazar.eu detail fetch failed id=%s",
                base.external_id,
                exc_info=True,
            )
            return base

        record = detail_record_from_html(html)
        if not record:
            return base
        # Detail pages omit sefName sometimes — keep list URL/id.
        if not record.get("id"):
            record = {**record, "id": base.external_id}
        if not record.get("sefName"):
            # Reconstruct sef from list URL path when possible.
            parts = base.url.rstrip("/").split("/")
            if len(parts) >= 2:
                record = {**record, "sefName": parts[-2]}

        enrich = fields_from_record(record, require_czech=True)
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
            "currency": base.currency,
            "image_url": base.image_url,
            "title": base.title,
            "published_at": base.published_at,
        }
        merged = merge_field_dicts(base_fields, enrich)
        merged["external_id"] = base.external_id
        merged["url"] = base.url
        dto = self._fields_to_dto(merged)
        return dto.model_copy(update={"observed_at": now_utc()})
