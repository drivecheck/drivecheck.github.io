"""Currency → CZK helpers for EU/PL portals.

Rate order: explicit `rates` arg → env `FX_CZK_PER_*` → last ECB snapshot
in-process → conservative stubs. Daily ECB sync writes `fx_rates` and loads
this process via `set_live_rates`.

FX conversions round to the nearest **100 CZK** (dealer-friendly; e.g.
254941 → 254900). Native CZK amounts stay whole koruny without hundred-rounding.
"""

from __future__ import annotations

import os
import re
from datetime import date
from typing import Mapping

# Conservative mid-market stubs — used only when ECB + env are missing.
_DEFAULT_RATES_TO_CZK: dict[str, float] = {
    "CZK": 1.0,
    "EUR": 25.0,
    "PLN": 5.8,
    "USD": 23.0,
}

_live_rates: dict[str, float] | None = None
_live_rate_date: date | None = None


def set_live_rates(rates: Mapping[str, float], quoted_on: date | None) -> None:
    global _live_rates, _live_rate_date
    _live_rates = {str(k).upper(): float(v) for k, v in rates.items() if float(v) > 0}
    _live_rate_date = quoted_on


def live_rate_date() -> date | None:
    return _live_rate_date


def live_rates() -> dict[str, float] | None:
    if _live_rates is None:
        return None
    return dict(_live_rates)


def clear_live_rates() -> None:
    global _live_rates, _live_rate_date
    _live_rates = None
    _live_rate_date = None


def _env_rate(currency: str) -> float | None:
    key = f"FX_CZK_PER_{currency.upper()}"
    raw = os.environ.get(key)
    if raw is None or not str(raw).strip():
        return None
    try:
        n = float(str(raw).replace(",", "."))
    except ValueError:
        return None
    if n <= 0:
        return None
    return n


def normalize_currency(code: str | None) -> str:
    if not code or not str(code).strip():
        return "CZK"
    raw = str(code).strip()
    aliases = {
        "KC": "CZK",
        "KČ": "CZK",
        "Kč": "CZK",
        "CZ": "CZK",
        "CZK": "CZK",
        "EURO": "EUR",
        "EUR": "EUR",
        "€": "EUR",
        "ZL": "PLN",
        "ZŁ": "PLN",
        "PLN": "PLN",
        "$": "USD",
        "USD": "USD",
    }
    if raw in aliases:
        return aliases[raw]
    c = re.sub(r"[^A-Za-z]", "", raw).upper()
    return aliases.get(c, c or "CZK")


def rate_to_czk(
    currency: str,
    *,
    rates: Mapping[str, float] | None = None,
) -> float:
    code = normalize_currency(currency)
    if rates is not None and code in rates:
        return float(rates[code])
    env = _env_rate(code)
    if env is not None:
        return env
    if _live_rates is not None and code in _live_rates:
        return float(_live_rates[code])
    if code in _DEFAULT_RATES_TO_CZK:
        return _DEFAULT_RATES_TO_CZK[code]
    raise ValueError(f"No CZK rate for currency '{currency}'")


def round_czk_to_hundred(amount: int | float) -> int:
    """Round positive CZK to nearest 100 (half-up). 254941.36 → 254900."""
    n = float(amount)
    if not (n > 0):
        raise ValueError("amount must be positive")
    # Half-up for positive amounts (avoid banker's round on *.50 hundreds).
    return int((n + 50.0) // 100.0 * 100.0)


def to_czk(
    amount: int | float,
    currency: str = "CZK",
    *,
    rates: Mapping[str, float] | None = None,
) -> int:
    """Convert amount in `currency` to integer CZK.

    - Native CZK: whole koruny (no hundred-rounding).
    - FX (EUR/PLN/…): convert then round to nearest 100 CZK for dealer display.
    """
    if amount is None:
        raise ValueError("amount is required")
    n = float(amount)
    if not (n > 0):
        raise ValueError("amount must be positive")
    code = normalize_currency(currency)
    if code == "CZK":
        return int(round(n))
    converted = n * rate_to_czk(code, rates=rates)
    return round_czk_to_hundred(converted)


def import_fx_fields(
    amount: int | float,
    currency: str,
    *,
    rates: Mapping[str, float] | None = None,
) -> dict[str, float | date | None]:
    """Metadata stored on import listings so nightly ECB re-quote can run."""
    code = normalize_currency(currency)
    if code == "CZK":
        return {
            "price_foreign": None,
            "fx_rate_date": None,
            "fx_czk_per_unit": None,
        }
    return {
        "price_foreign": float(amount),
        "fx_rate_date": live_rate_date(),
        "fx_czk_per_unit": rate_to_czk(code, rates=rates),
    }
