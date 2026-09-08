from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import ceil, floor
from zoneinfo import ZoneInfo

from drivecheck_crawler.catalog.normalize import (
    display_make,
    map_body,
    map_fuel,
    normalize_key,
)

FUEL_BIT = 1
TRANSMISSION_BIT = 2
BODY_BIT = 4


@dataclass(frozen=True)
class MarketListingRow:
    category: str
    make: str
    model: str
    year: int | None
    fuel: str | None
    transmission: str | None
    body: str | None
    price_czk: int


@dataclass(frozen=True)
class DailyMarketAggregate:
    observed_date: date
    category_key: str
    make_key: str
    model_key: str
    year: int
    dimension_mask: int
    fuel_key: str
    transmission_key: str
    body_key: str
    p25_czk: int
    median_czk: int
    p75_czk: int
    active_count: int


def percentile(sorted_values: list[int], fraction: float) -> int:
    index = (len(sorted_values) - 1) * fraction
    low, high = floor(index), ceil(index)
    if low == high:
        return sorted_values[low]
    weight = index - low
    return round(sorted_values[low] * (1 - weight) + sorted_values[high] * weight)


def build_daily_aggregates(
    rows: list[MarketListingRow], observed_date: date
) -> list[DailyMarketAggregate]:
    grouped: dict[tuple[str, str, str, int, int, str, str, str], list[int]] = {}
    for item in rows:
        if (
            not item.make.strip()
            or not item.model.strip()
            or item.year is None
            or item.price_czk < 5_000
            or item.price_czk > 50_000_000
        ):
            continue
        canonical_make = display_make(item.make)
        if not canonical_make:
            continue
        category = normalize_key(item.category or "passenger")
        make = normalize_key(canonical_make)
        model = normalize_key(item.model)
        fuel = normalize_key(map_fuel(item.fuel))
        transmission = normalize_key(item.transmission or "Neuvedeno")
        body = normalize_key(map_body(item.body, category))
        for mask in range(8):
            key = (
                category,
                make,
                model,
                item.year,
                mask,
                fuel if mask & FUEL_BIT else "",
                transmission if mask & TRANSMISSION_BIT else "",
                body if mask & BODY_BIT else "",
            )
            grouped.setdefault(key, []).append(item.price_czk)

    result: list[DailyMarketAggregate] = []
    for key, prices in grouped.items():
        values = sorted(prices)
        result.append(
            DailyMarketAggregate(
                observed_date,
                *key,
                percentile(values, 0.25),
                percentile(values, 0.5),
                percentile(values, 0.75),
                len(values),
            )
        )
    return result


def record_daily_market_aggregates(repo, observed_at: datetime) -> int:
    market_date = observed_at.astimezone(ZoneInfo("Europe/Prague")).date()
    rows = repo.fetch_active_market_rows(observed_at, max_age_days=7)
    aggregates = build_daily_aggregates(rows, market_date)
    repo.upsert_market_price_daily(aggregates)
    return len(aggregates)
