"""Normalize marketplace prices to a comparable CZK asking price (incl. VAT)."""

from __future__ import annotations

from dataclasses import dataclass

from drivecheck_crawler.normalize import parse_int, parse_price_czk

# Standard Czech VAT rate for used-car dealer offers.
CZ_VAT_MULTIPLIER = 1.21


@dataclass(frozen=True)
class ResolvedPrices:
    """price_czk is always the comparable consumer/dealer ask including VAT when possible."""

    price_czk: int
    price_without_vat_czk: int | None
    vat_deductible: bool | None
    price_includes_vat: bool | None


def _valid_price(value: object) -> int | None:
    return parse_price_czk(value)


def resolve_sauto_prices(
    *,
    price: object,
    price_without_vat: object = None,
    price_is_without_vat: object = None,
    price_is_vat_deductible: object = None,
) -> ResolvedPrices | None:
    """
    Sauto usually publishes `price` including VAT and optionally `price_without_vat`.
    When `price_is_without_vat` is true, `price` is excl. VAT and must be grossed up
    for market comparisons.
    """
    listed = _valid_price(price)
    if listed is None:
        return None

    without_raw = parse_int(price_without_vat)
    without = _valid_price(without_raw) if without_raw is not None else None

    is_without = price_is_without_vat is True
    deductible: bool | None
    if isinstance(price_is_vat_deductible, bool):
        deductible = price_is_vat_deductible
    else:
        deductible = None

    if is_without:
        # Source ask is excl. VAT — store both; comps use incl. VAT.
        with_vat = int(round(listed * CZ_VAT_MULTIPLIER))
        if not (5_000 <= with_vat <= 50_000_000):
            return None
        return ResolvedPrices(
            price_czk=with_vat,
            price_without_vat_czk=listed,
            vat_deductible=True if deductible is None else deductible,
            price_includes_vat=False,
        )

    # Typical path: listed price includes VAT (or VAT unknown).
    includes_vat: bool | None
    if without is not None and without < listed:
        includes_vat = True
    elif deductible is True:
        includes_vat = True
    else:
        includes_vat = None

    return ResolvedPrices(
        price_czk=listed,
        price_without_vat_czk=without,
        vat_deductible=deductible,
        price_includes_vat=includes_vat,
    )
