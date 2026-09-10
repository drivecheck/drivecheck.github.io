from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

from drivecheck_crawler.adapters.base import SourceAdapter
from drivecheck_crawler.config import CrawlerConfig
from drivecheck_crawler.cursors import CrawlCursorStore
from drivecheck_crawler.features import normalize_feature_list
from drivecheck_crawler.http_client import RateLimitedClient
from drivecheck_crawler.listing_quality import should_reject_as_leasing
from drivecheck_crawler.models import ListingDTO
from drivecheck_crawler.normalize import (
    cb_name,
    map_seller_type,
    now_utc,
    parse_datetime,
    parse_int,
    parse_year,
)
from drivecheck_crawler.prices import resolve_sauto_prices

logger = logging.getLogger(__name__)

SAUTO_SEARCH = "https://www.sauto.cz/api/v1/items/search"
SAUTO_ITEM = "https://www.sauto.cz/api/v1/items/{item_id}"
SAUTO_REFERER = "https://www.sauto.cz/"
CATEGORY_OSOBNI = 838

# Sauto search rejects offset >= 10000 with HTTP 422 too_high_offset.
OFFSET_WALL = 10_000

# Cover osobní inventory: ojete (~80k) + nove (~18k) + predvadeci (~4k) ≈ 103k.
SAUTO_CONDITIONS = ("ojete", "nove", "predvadeci")

# Price edges (CZK). Adjacent bands use exclusive upper bound (next_edge - 1)
# so listings on a boundary are not double-counted across slices.
# Mid-market steps are finer so each slice stays under the offset wall.
PRICE_EDGES: list[int | None] = [
    0,
    50_000,
    100_000,
    150_000,
    200_000,
    250_000,
    300_000,
    350_000,
    400_000,
    450_000,
    500_000,
    600_000,
    700_000,
    800_000,
    1_000_000,
    1_250_000,
    1_500_000,
    2_000_000,
    3_000_000,
    5_000_000,
    None,
]


def default_slices(
    *,
    conditions: tuple[str, ...] = SAUTO_CONDITIONS,
    price_edges: list[int | None] | None = None,
) -> list[dict[str, Any]]:
    edges = price_edges if price_edges is not None else PRICE_EDGES
    slices: list[dict[str, Any]] = []
    for condition in conditions:
        for idx in range(len(edges) - 1):
            price_from = int(edges[idx] or 0)
            next_edge = edges[idx + 1]
            price_to = None if next_edge is None else int(next_edge) - 1
            slices.append(
                {
                    "condition": condition,
                    "price_from": price_from,
                    "price_to": price_to,
                }
            )
    return slices


def bisect_slice(slice_: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Split a price band into two non-overlapping halves. Returns None if too narrow."""
    condition = str(slice_.get("condition") or "ojete")
    price_from = int(slice_.get("price_from") or 0)
    raw_to = slice_.get("price_to")
    price_to = int(raw_to) if raw_to is not None else None

    if price_to is None:
        # Open-ended top: introduce a midpoint above the floor.
        span = max(500_000, price_from // 2 or 1)
        mid = price_from + span
        left = {"condition": condition, "price_from": price_from, "price_to": mid}
        right = {"condition": condition, "price_from": mid + 1, "price_to": None}
        return left, right

    if price_to <= price_from:
        return None
    mid = (price_from + price_to) // 2
    if mid < price_from or mid >= price_to:
        return None
    left = {"condition": condition, "price_from": price_from, "price_to": mid}
    right = {"condition": condition, "price_from": mid + 1, "price_to": price_to}
    return left, right


def search_params_for_slice(
    slice_: dict[str, Any],
    *,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
        "condition_seo": slice_.get("condition") or "ojete",
        "category_id": CATEGORY_OSOBNI,
        "operating_lease": "false",
        "price_from": int(slice_.get("price_from") or 0),
    }
    price_to = slice_.get("price_to")
    if price_to is not None:
        params["price_to"] = int(price_to)
    return params


def advance_after_page(
    *,
    slices: list[dict[str, Any]],
    slice_idx: int,
    offset: int,
    page_len: int,
    total: int,
) -> tuple[list[dict[str, Any]], int, int, str]:
    """
    Advance cursor after a successful page.

    Returns (slices, slice_idx, offset, action) where action is one of:
    next_page | rotate | bisect | stuck.
    """
    if not slices:
        return default_slices(), 0, 0, "rotate"

    idx = slice_idx % len(slices)
    next_offset = offset + page_len

    # Slice exhausted (or empty page already handled by caller).
    if page_len == 0 or next_offset >= total:
        next_idx = (idx + 1) % len(slices)
        return slices, next_idx, 0, "rotate"

    # Approaching API offset wall — must not request offset >= OFFSET_WALL.
    if next_offset >= OFFSET_WALL:
        split = bisect_slice(slices[idx])
        if split is None:
            next_idx = (idx + 1) % len(slices)
            return slices, next_idx, 0, "stuck"
        left, right = split
        new_slices = list(slices)
        new_slices[idx : idx + 1] = [left, right]
        return new_slices, idx, 0, "bisect"

    return slices, idx, next_offset, "next_page"


def maybe_bisect_oversized(
    *,
    slices: list[dict[str, Any]],
    slice_idx: int,
    total: int,
) -> tuple[list[dict[str, Any]], int, int, bool]:
    """If total exceeds what offset can cover, bisect current slice in place."""
    if total <= OFFSET_WALL or not slices:
        return slices, slice_idx, 0, False
    idx = slice_idx % len(slices)
    split = bisect_slice(slices[idx])
    if split is None:
        return slices, (idx + 1) % len(slices), 0, False
    left, right = split
    new_slices = list(slices)
    new_slices[idx : idx + 1] = [left, right]
    return new_slices, idx, 0, True


class SautoAdapter(SourceAdapter):
    source = "sauto"

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
        cursor = self._cursors.get("sauto")
        slices, slice_idx, offset = self._load_cursor(cursor)
        pages = 0
        # Guard against pathological bisect loops within one run.
        bisects_this_run = 0
        max_bisects = 32

        while pages < max_pages:
            if not slices:
                slices = default_slices()
                slice_idx = 0
                offset = 0

            slice_idx = slice_idx % len(slices)
            current = slices[slice_idx]

            # Never request an offset the API will reject.
            if offset >= OFFSET_WALL:
                slices, slice_idx, offset, bisected = maybe_bisect_oversized(
                    slices=slices, slice_idx=slice_idx, total=OFFSET_WALL + 1
                )
                if bisected:
                    bisects_this_run += 1
                else:
                    slice_idx = (slice_idx + 1) % len(slices)
                    offset = 0
                self._save_cursor(slices, slice_idx, offset, total=None)
                continue

            params = search_params_for_slice(
                current,
                offset=offset,
                limit=self._config.sauto_page_size,
            )
            payload = self._client.get_json(
                SAUTO_SEARCH,
                params=params,
                referer=SAUTO_REFERER,
            )
            results = payload.get("results") or []
            pagination = payload.get("pagination") or {}
            total = int(pagination.get("total") or 0)

            # Adaptive split when a band still overflows the wall.
            if total > OFFSET_WALL and offset == 0:
                slices, slice_idx, offset, bisected = maybe_bisect_oversized(
                    slices=slices, slice_idx=slice_idx, total=total
                )
                if bisected and bisects_this_run < max_bisects:
                    bisects_this_run += 1
                    logger.info(
                        "sauto bisect condition=%s price_from=%s price_to=%s total=%s",
                        current.get("condition"),
                        current.get("price_from"),
                        current.get("price_to"),
                        total,
                    )
                    self._save_cursor(slices, slice_idx, offset, total=total)
                    continue
                if not bisected:
                    # Cannot split further — walk what we can, then rotate.
                    pass

            if not results:
                slice_idx = (slice_idx + 1) % len(slices)
                offset = 0
                self._save_cursor(slices, slice_idx, offset, total=total)
                pages += 1
                continue

            for row in results:
                dto = self._map_search_row(row)
                if dto is None:
                    continue
                if self._config.sauto_fetch_details:
                    yield self._enrich_from_detail(dto)
                else:
                    yield dto

            slices, slice_idx, offset, action = advance_after_page(
                slices=slices,
                slice_idx=slice_idx,
                offset=offset,
                page_len=len(results),
                total=total,
            )
            if action == "bisect":
                bisects_this_run += 1
                logger.info(
                    "sauto bisect at offset wall condition=%s price_from=%s price_to=%s",
                    current.get("condition"),
                    current.get("price_from"),
                    current.get("price_to"),
                )
            pages += 1
            self._save_cursor(slices, slice_idx, offset, total=total)

    def _load_cursor(
        self, cursor: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], int, int]:
        raw_slices = cursor.get("slices")
        if isinstance(raw_slices, list) and raw_slices:
            slices = [s for s in raw_slices if isinstance(s, dict)]
        else:
            slices = default_slices()
        if not slices:
            slices = default_slices()
        slice_idx = int(cursor.get("slice_idx", 0)) % len(slices)
        offset = int(cursor.get("offset", 0))
        # Migrate legacy single-offset cursor (pre-partition) to slice 0.
        if "slice_idx" not in cursor and "slices" not in cursor:
            offset = 0
            slice_idx = 0
        return slices, slice_idx, offset

    def _save_cursor(
        self,
        slices: list[dict[str, Any]],
        slice_idx: int,
        offset: int,
        *,
        total: int | None,
    ) -> None:
        current = slices[slice_idx % len(slices)] if slices else {}
        payload: dict[str, Any] = {
            "slice_idx": slice_idx % len(slices) if slices else 0,
            "offset": offset,
            "slices": slices,
            "condition": current.get("condition"),
            "price_from": current.get("price_from"),
            "price_to": current.get("price_to"),
        }
        if total is not None:
            payload["total"] = total
        self._cursors.set("sauto", payload)

    def _map_search_row(self, row: dict[str, Any]) -> ListingDTO | None:
        item_id = row.get("id")
        # Search payload usually lacks VAT flags; detail enrich fills them.
        prices = resolve_sauto_prices(price=row.get("price"))
        if item_id is None or prices is None:
            return None
        if should_reject_as_leasing(
            None, flags={"operating_lease": row.get("operating_lease")}
        ):
            return None

        manufacturer = row.get("manufacturer_cb") or {}
        model = row.get("model_cb") or {}
        make_seo = manufacturer.get("seo_name") or "auto"
        model_seo = model.get("seo_name") or "model"
        url = f"https://www.sauto.cz/osobni/detail/{quote(str(make_seo))}/{quote(str(model_seo))}/{item_id}"

        locality = row.get("locality") or {}
        region = locality.get("region") or locality.get("district")

        year = parse_year(row.get("manufacturing_date")) or parse_year(row.get("in_operation_date"))
        image_url = _first_image_url(row)
        title_parts = [cb_name(manufacturer), cb_name(model), row.get("additional_model_name")]
        title = " ".join(str(p) for p in title_parts if p)

        return ListingDTO(
            source="sauto",
            external_id=str(item_id),
            url=url,
            make=cb_name(manufacturer),
            model=cb_name(model),
            trim=row.get("additional_model_name"),
            year=year,
            mileage_km=parse_int(row.get("tachometer")),
            fuel=cb_name(row.get("fuel_cb")),
            transmission=cb_name(row.get("gearbox_cb")),
            seller_type=map_seller_type(premise=row.get("premise")),
            region=region,
            price_czk=prices.price_czk,
            price_without_vat_czk=prices.price_without_vat_czk,
            vat_deductible=prices.vat_deductible,
            price_includes_vat=prices.price_includes_vat,
            feature_keys=[],
            image_url=image_url,
            title=title or None,
            published_at=parse_datetime(row.get("create_date") or row.get("sorting_date")),
            observed_at=now_utc(),
        )

    def _enrich_from_detail(self, base: ListingDTO) -> ListingDTO:
        try:
            payload = self._client.get_json(
                SAUTO_ITEM.format(item_id=base.external_id),
                referer=base.url,
            )
        except Exception:
            return base

        result = payload.get("result") or {}
        if not result:
            return base

        # Explicitly ignore phone / user / description / vin / address fields.
        equipment = result.get("equipment_cb") or []
        feature_names = [e.get("name", "") for e in equipment if isinstance(e, dict)]
        features = normalize_feature_list(feature_names)

        locality = result.get("locality") or {}
        region = locality.get("region") or locality.get("district") or base.region

        prices = resolve_sauto_prices(
            price=result.get("price"),
            price_without_vat=result.get("price_without_vat"),
            price_is_without_vat=result.get("price_is_without_vat"),
            price_is_vat_deductible=result.get("price_is_vat_deductible"),
        )

        update: dict[str, Any] = {
            "make": cb_name(result.get("manufacturer_cb")) or base.make,
            "model": cb_name(result.get("model_cb")) or base.model,
            "trim": result.get("additional_model_name") or base.trim,
            "year": parse_year(result.get("manufacturing_date")) or base.year,
            "mileage_km": parse_int(result.get("tachometer")) or base.mileage_km,
            "fuel": cb_name(result.get("fuel_cb")) or base.fuel,
            "transmission": cb_name(result.get("gearbox_cb")) or base.transmission,
            "drive": cb_name(result.get("drive_cb")) or base.drive,
            "power_kw": parse_int(result.get("engine_power")) or base.power_kw,
            "displacement_cc": parse_int(result.get("engine_volume")) or base.displacement_cc,
            "body": cb_name(result.get("vehicle_body_cb")) or base.body,
            "seller_type": map_seller_type(premise=result.get("premise")),
            "region": region,
            "feature_keys": features,
            "image_url": _first_image_url(result) or base.image_url,
            "doors": parse_int(result.get("doors")) or base.doors,
            "color": cb_name(result.get("color_cb")) or base.color,
            "first_owner": (
                result.get("first_owner")
                if isinstance(result.get("first_owner"), bool)
                else base.first_owner
            ),
            "service_book": (
                result.get("service_book")
                if isinstance(result.get("service_book"), bool)
                else base.service_book
            ),
            "country_of_origin": cb_name(result.get("country_of_origin_cb"))
            or base.country_of_origin,
            "published_at": parse_datetime(result.get("create_date") or result.get("sorting_date"))
            or base.published_at,
            "observed_at": now_utc(),
        }
        if prices is not None:
            update.update(
                {
                    "price_czk": prices.price_czk,
                    "price_without_vat_czk": prices.price_without_vat_czk,
                    "vat_deductible": prices.vat_deductible,
                    "price_includes_vat": prices.price_includes_vat,
                }
            )

        return base.model_copy(update=update)


def _absolutize_media_url(value: str | None) -> str | None:
    if not value:
        return None
    url = value.strip()
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return None


def _first_image_url(row: dict[str, Any]) -> str | None:
    for key in ("image", "thumbnail", "photo", "main_image"):
        val = row.get(key)
        if isinstance(val, str):
            abs_url = _absolutize_media_url(val)
            if abs_url:
                return abs_url
        if isinstance(val, dict):
            for nested in ("url", "src", "large", "small"):
                abs_url = _absolutize_media_url(val.get(nested) if isinstance(val.get(nested), str) else None)
                if abs_url:
                    return abs_url
    images = row.get("images") or row.get("photos") or []
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, str):
            abs_url = _absolutize_media_url(first)
            if abs_url:
                return abs_url
        if isinstance(first, dict):
            for nested in ("url", "src", "large", "small"):
                abs_url = _absolutize_media_url(
                    first.get(nested) if isinstance(first.get(nested), str) else None
                )
                if abs_url:
                    return abs_url
    return None
