from datetime import date

from drivecheck_crawler.market_aggregate import (
    BODY_BIT,
    FUEL_BIT,
    TRANSMISSION_BIT,
    MarketListingRow,
    build_daily_aggregates,
)


def row(price: int, *, make: str = "Škoda", model: str = "Octavia") -> MarketListingRow:
    return MarketListingRow(
        category="passenger",
        make=make,
        model=model,
        year=2020,
        fuel="Nafta",
        transmission="Manuální",
        body="Kombi",
        price_czk=price,
    )


def test_builds_coarse_and_detailed_rollups() -> None:
    result = build_daily_aggregates(
        [row(200_000), row(250_000), row(300_000), row(350_000)],
        date(2026, 8, 4),
    )
    masks = {item.dimension_mask for item in result}
    assert masks == set(range(8))
    coarse = next(item for item in result if item.dimension_mask == 0)
    detailed = next(
        item
        for item in result
        if item.dimension_mask == FUEL_BIT | TRANSMISSION_BIT | BODY_BIT
    )
    assert (coarse.p25_czk, coarse.median_czk, coarse.p75_czk) == (
        237_500,
        275_000,
        312_500,
    )
    assert detailed.active_count == 4
    assert detailed.make_key == "skoda"
    assert detailed.model_key == "octavia"
    assert detailed.fuel_key == "nafta"
    assert detailed.body_key == "kombi"


def test_drops_rows_without_identity_year_or_valid_czk_price() -> None:
    bad = [
        row(4_999),
        row(50_000_001),
        row(250_000, make=""),
        MarketListingRow("passenger", "Škoda", "Octavia", None, "Nafta", "Manuální", "Kombi", 250_000),
    ]
    assert build_daily_aggregates(bad, date(2026, 8, 4)) == []
