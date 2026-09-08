from __future__ import annotations

from typing import Any

from drivecheck_crawler.adapters.sauto import (
    OFFSET_WALL,
    SAUTO_CONDITIONS,
    SautoAdapter,
    advance_after_page,
    bisect_slice,
    default_slices,
    maybe_bisect_oversized,
    search_params_for_slice,
)
from drivecheck_crawler.config import CrawlerConfig


class MemoryCursor:
    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self.store: dict[str, dict[str, Any]] = {}
        if initial is not None:
            self.store["sauto"] = dict(initial)

    def get(self, key: str) -> dict[str, Any]:
        return dict(self.store.get(key) or {})

    def set(self, key: str, value: dict[str, Any]) -> None:
        self.store[key] = dict(value)


class FakeSearchClient:
    """Return canned search pages keyed by (condition, price_from, price_to, offset)."""

    def __init__(self, pages: dict[tuple[Any, ...], dict[str, Any]]) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    def get_json(self, url: str, *, params: dict[str, Any] | None = None, referer=None):
        assert params is not None
        self.calls.append(dict(params))
        key = (
            params.get("condition_seo"),
            int(params.get("price_from") or 0),
            params.get("price_to"),
            int(params.get("offset") or 0),
        )
        if key not in self.pages:
            # Default empty page for unknown slices.
            return {"results": [], "pagination": {"total": 0, "offset": key[3], "limit": 40}}
        return self.pages[key]


def test_default_slices_cover_conditions_and_non_overlapping_bands():
    slices = default_slices()
    conditions = {s["condition"] for s in slices}
    assert conditions == set(SAUTO_CONDITIONS)

    ojete = [s for s in slices if s["condition"] == "ojete"]
    assert ojete[0]["price_from"] == 0
    assert ojete[0]["price_to"] == 49_999
    assert ojete[1]["price_from"] == 50_000
    # Open-ended last band
    assert ojete[-1]["price_to"] is None
    assert ojete[-1]["price_from"] == 5_000_000

    # No overlapping adjacent closed bands
    for left, right in zip(ojete, ojete[1:], strict=False):
        if left["price_to"] is None or right["price_to"] is None:
            continue
        assert left["price_to"] + 1 == right["price_from"]


def test_bisect_slice_splits_closed_and_open_ranges():
    left, right = bisect_slice({"condition": "ojete", "price_from": 100_000, "price_to": 199_999})
    assert left == {"condition": "ojete", "price_from": 100_000, "price_to": 149_999}
    assert right == {"condition": "ojete", "price_from": 150_000, "price_to": 199_999}

    left, right = bisect_slice({"condition": "nove", "price_from": 5_000_000, "price_to": None})
    assert left["price_from"] == 5_000_000
    # Open-end midpoint uses max(500k, price_from // 2) above the floor.
    assert left["price_to"] == 7_500_000
    assert right == {"condition": "nove", "price_from": 7_500_001, "price_to": None}

    assert bisect_slice({"condition": "ojete", "price_from": 10, "price_to": 10}) is None


def test_search_params_for_slice_omits_open_price_to():
    params = search_params_for_slice(
        {"condition": "predvadeci", "price_from": 5_000_000, "price_to": None},
        offset=40,
        limit=40,
    )
    assert params["condition_seo"] == "predvadeci"
    assert params["price_from"] == 5_000_000
    assert "price_to" not in params
    assert params["offset"] == 40
    assert params["operating_lease"] == "false"


def test_advance_after_page_rotates_and_respects_offset_wall():
    slices = [
        {"condition": "ojete", "price_from": 0, "price_to": 49_999},
        {"condition": "ojete", "price_from": 50_000, "price_to": 99_999},
    ]

    # Normal next page
    s, idx, off, action = advance_after_page(
        slices=slices, slice_idx=0, offset=0, page_len=40, total=200
    )
    assert action == "next_page"
    assert (idx, off) == (0, 40)

    # Exhausted slice
    s, idx, off, action = advance_after_page(
        slices=slices, slice_idx=0, offset=160, page_len=40, total=200
    )
    assert action == "rotate"
    assert (idx, off) == (1, 0)

    # Offset wall → bisect current slice
    fat = [{"condition": "ojete", "price_from": 0, "price_to": 999_999}]
    s, idx, off, action = advance_after_page(
        slices=fat, slice_idx=0, offset=OFFSET_WALL - 40, page_len=40, total=20_000
    )
    assert action == "bisect"
    assert off == 0
    assert idx == 0
    assert len(s) == 2
    assert s[0]["price_to"] < s[1]["price_from"]


def test_maybe_bisect_oversized_only_when_over_wall():
    slices = [{"condition": "ojete", "price_from": 0, "price_to": 999_999}]
    s, idx, off, did = maybe_bisect_oversized(slices=slices, slice_idx=0, total=OFFSET_WALL)
    assert did is False
    assert s is slices

    s, idx, off, did = maybe_bisect_oversized(slices=slices, slice_idx=0, total=OFFSET_WALL + 1)
    assert did is True
    assert len(s) == 2
    assert off == 0


def test_iter_listings_rotates_slices_and_never_requests_offset_wall():
    # Tiny matrix: two slices. First has 80 listings (2 pages of 40), second empty.
    pages = {
        ("ojete", 0, 49_999, 0): {
            "results": [{"id": i, "price": 10_000 + i} for i in range(1, 41)],
            "pagination": {"total": 80, "offset": 0, "limit": 40},
        },
        ("ojete", 0, 49_999, 40): {
            "results": [{"id": i, "price": 10_000 + i} for i in range(41, 81)],
            "pagination": {"total": 80, "offset": 40, "limit": 40},
        },
        ("ojete", 50_000, 99_999, 0): {
            "results": [],
            "pagination": {"total": 0, "offset": 0, "limit": 40},
        },
    }
    client = FakeSearchClient(pages)
    cursors = MemoryCursor(
        {
            "slice_idx": 0,
            "offset": 0,
            "slices": [
                {"condition": "ojete", "price_from": 0, "price_to": 49_999},
                {"condition": "ojete", "price_from": 50_000, "price_to": 99_999},
            ],
        }
    )
    adapter = SautoAdapter(
        client=client,  # type: ignore[arg-type]
        config=CrawlerConfig(sauto_fetch_details=False, sauto_page_size=40),
        cursors=cursors,  # type: ignore[arg-type]
    )

    ids = [dto.external_id for dto in adapter.iter_listings(max_pages=3)]
    assert ids == [str(i) for i in range(1, 81)]

    offsets = [c["offset"] for c in client.calls]
    assert all(o < OFFSET_WALL for o in offsets)
    assert ("ojete", 50_000, 99_999, 0) in {
        (c["condition_seo"], c["price_from"], c.get("price_to"), c["offset"]) for c in client.calls
    }
    # After empty second slice, cursor rotates back toward first
    saved = cursors.get("sauto")
    assert saved["slice_idx"] == 0
    assert saved["offset"] == 0


def test_iter_listings_bisects_when_total_exceeds_wall():
    # First response: oversized band. After bisect, left half is crawlable.
    pages: dict[tuple[Any, ...], dict[str, Any]] = {
        ("ojete", 0, 999_999, 0): {
            "results": [{"id": 1, "price": 120_000}],
            "pagination": {"total": OFFSET_WALL + 500, "offset": 0, "limit": 40},
        },
        ("ojete", 0, 499_999, 0): {
            "results": [{"id": 10, "price": 120_000}],
            "pagination": {"total": 50, "offset": 0, "limit": 40},
        },
    }
    client = FakeSearchClient(pages)
    cursors = MemoryCursor(
        {
            "slice_idx": 0,
            "offset": 0,
            "slices": [{"condition": "ojete", "price_from": 0, "price_to": 999_999}],
        }
    )
    adapter = SautoAdapter(
        client=client,  # type: ignore[arg-type]
        config=CrawlerConfig(sauto_fetch_details=False, sauto_page_size=40),
        cursors=cursors,  # type: ignore[arg-type]
    )

    ids = [dto.external_id for dto in adapter.iter_listings(max_pages=2)]
    assert "10" in ids
    # Oversized probe happened, then bisected band was fetched (no offset>=wall).
    assert all(c["offset"] < OFFSET_WALL for c in client.calls)
    saved = cursors.get("sauto")
    assert len(saved["slices"]) >= 2


def test_legacy_cursor_resets_offset_on_partition_migrate():
    cursors = MemoryCursor({"offset": 9999, "total": 80000})
    adapter = SautoAdapter(
        client=FakeSearchClient({}),  # type: ignore[arg-type]
        config=CrawlerConfig(sauto_fetch_details=False),
        cursors=cursors,  # type: ignore[arg-type]
    )
    slices, slice_idx, offset = adapter._load_cursor(cursors.get("sauto"))
    assert offset == 0
    assert slice_idx == 0
    assert len(slices) == len(default_slices())
