"""Parse and fetch the ECB eurofxref daily XML (EUR-based quotes)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from typing import Mapping

ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"


def parse_ecb_daily_xml(xml_text: str) -> tuple[date, dict[str, float]]:
    """Return (quoted_on, CZK per 1 unit of currency).

    ECB quotes units of each currency per 1 EUR. We invert through CZK.
    """
    root = ET.fromstring(xml_text)
    quoted_on: date | None = None
    per_eur: dict[str, float] = {}
    for cube in root.iter():
        if not cube.tag.endswith("Cube"):
            continue
        time_raw = cube.get("time")
        if time_raw:
            quoted_on = date.fromisoformat(time_raw)
        currency = cube.get("currency")
        rate_raw = cube.get("rate")
        if currency and rate_raw:
            per_eur[currency.strip().upper()] = float(rate_raw)

    if quoted_on is None:
        raise ValueError("ECB XML missing quote date")
    czk_per_eur = per_eur.get("CZK")
    if czk_per_eur is None or czk_per_eur <= 0:
        raise ValueError("ECB XML missing CZK rate")

    czk_per_unit: dict[str, float] = {"EUR": czk_per_eur, "CZK": 1.0}
    for currency, units_per_eur in per_eur.items():
        if currency == "CZK" or units_per_eur <= 0:
            continue
        czk_per_unit[currency] = czk_per_eur / units_per_eur
    return quoted_on, czk_per_unit


def rates_from_eur_cross(czk_per_eur: float, per_eur: Mapping[str, float]) -> dict[str, float]:
    """Test helper: build CZK-per-unit map from EUR crosses."""
    out = {"EUR": float(czk_per_eur), "CZK": 1.0}
    for currency, units_per_eur in per_eur.items():
        if currency == "CZK" or units_per_eur <= 0:
            continue
        out[currency.upper()] = float(czk_per_eur) / float(units_per_eur)
    return out
