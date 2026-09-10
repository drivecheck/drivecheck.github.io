"""Ingest gate: whole cars for sale only — not parts, leases, or garbage fields.

Used by seed/upsert, live search, and Bazos purge. Soft-hide existing junk
via ``status=removed``; never DELETE listing rows.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

# Match extractors / import portals: passenger-car comps window.
_YEAR_MIN = 1990
_MILEAGE_MIN = 1
_MILEAGE_MAX = 1_500_000
_PRICE_MIN_CZK = 5_000
_PRICE_MAX_CZK = 50_000_000

_LEASE_FLAG_KEYS = frozenset(
    {
        "operatinglease",
        "isoperatinglease",
        "operating_lease",
        "lease",
        "leasing",
        "subscription",
        "carsubscription",
    }
)

_TRUE_STRINGS = frozenset({"1", "true", "yes", "ja", "y"})


@dataclass(frozen=True, slots=True)
class IngestReject:
    reason: str


def _fold(text: str) -> str:
    if not text:
        return ""
    norm = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in norm if unicodedata.category(ch) != "Mn")


def _first_line(popis: str | None) -> str:
    if not popis:
        return ""
    for line in popis.replace("\r", "\n").split("\n"):
        cleaned = line.strip()
        if cleaned:
            return cleaned[:240]
    return popis.strip()[:240]


def _headline(title: str | None, popis: str | None) -> str:
    t = (title or "").strip()
    head = _first_line(popis)
    if not head:
        return t
    if not t:
        return head
    return f"{t}\n{head}"


# Sale that merely *offers* credit — still a buyable car (keep).
_FINANCE_OPTION = re.compile(
    r"(?:"
    r"moznost\s+(?:operativniho\s+|financniho\s+)?leasing"
    r"|\bfinancovani\b"
    r"|\blze\s+(?:i\s+)?na\s+splatky"
    r"|\bsplatky\s+mozne"
    r"|\buver\b"
    r")"
)

# The listing *is* a lease / subscription (reject).
_LEASE_PRODUCT = re.compile(
    r"(?:"
    r"\boperak"
    r"|\bpredplatn"
    r"|na\s+splatky\s+formou\s+operak"
    r"|formou\s+operak"
    r"|kc\s*/\s*mes"
    r"|/\s*mesic"
    r"|mesicni\s+splatka"
    r"|leasingrat"
    r"|eur\s*/\s*(?:monat|month|mes)"
    r"|€\s*/\s*(?:monat|month)"
    r"|car\s+subscription"
    r"|autoabo\b"
    r"|operativni\s+pronajem"
    r"|pronajem\s+(?:vozidla|auta|automobilu)"
    r")"
)

_OPERATING_LEASE_PHRASE = re.compile(
    r"(?:"
    r"operativni\s+leasing"
    r"|operating\s+lease"
    r")"
)


def _truthy_flag(value: object) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, (int, float)) and value == 1:
        return True
    if isinstance(value, str):
        return _fold(value).replace(" ", "") in _TRUE_STRINGS
    return False


def _flags_say_lease(flags: Mapping[str, Any] | None) -> bool:
    if not flags:
        return False
    for key, value in flags.items():
        nk = _fold(str(key)).replace(" ", "").replace("_", "").replace("-", "")
        if nk in {k.replace("_", "") for k in _LEASE_FLAG_KEYS} and _truthy_flag(value):
            return True
    return False


def should_reject_as_leasing(
    title: str | None,
    popis: str | None = None,
    *,
    flags: Mapping[str, Any] | None = None,
) -> IngestReject | None:
    """Return reject reason when the ad is a lease/subscription, not a sale."""
    if _flags_say_lease(flags):
        return IngestReject(reason="operating_lease_flag")

    folded = _fold(_headline(title, popis))
    if not folded.strip():
        return None

    if _LEASE_PRODUCT.search(folded):
        return IngestReject(reason="lease_product")

    if _OPERATING_LEASE_PHRASE.search(folded) and not _FINANCE_OPTION.search(folded):
        return IngestReject(reason="operating_lease")

    return None


def _year_max() -> int:
    return date.today().year + 1


def should_reject_implausible_fields(
    *,
    price_czk: int | None = None,
    year: int | None = None,
    mileage_km: int | None = None,
) -> IngestReject | None:
    """Reject extracted values that cannot be a normal passenger-car listing."""
    if year is not None and not (_YEAR_MIN <= year <= _year_max()):
        return IngestReject(reason="implausible_year")
    if mileage_km is not None and not (_MILEAGE_MIN <= mileage_km <= _MILEAGE_MAX):
        return IngestReject(reason="implausible_mileage")
    if price_czk is not None and not (_PRICE_MIN_CZK <= price_czk <= _PRICE_MAX_CZK):
        return IngestReject(reason="implausible_price")
    return None


def should_reject_listing(
    *,
    title: str | None = None,
    popis: str | None = None,
    price_czk: int | None = None,
    year: int | None = None,
    mileage_km: int | None = None,
    url: str | None = None,
    flags: Mapping[str, Any] | None = None,
) -> IngestReject | None:
    """Single ingest gate used before upsert. None = ok to store as a car sale."""
    lease = should_reject_as_leasing(title, popis, flags=flags)
    if lease is not None:
        return IngestReject(reason=f"leasing:{lease.reason}")

    # Late import: adapters.__init__ loads BazosAdapter which imports this module.
    from drivecheck_crawler.adapters.bazos_parts_filter import should_reject_as_parts

    parts = should_reject_as_parts(title, popis, price_czk, url=url)
    if parts is not None:
        return IngestReject(reason=f"parts:{parts.reason}")

    fields = should_reject_implausible_fields(
        price_czk=price_czk, year=year, mileage_km=mileage_km
    )
    if fields is not None:
        return IngestReject(reason=f"fields:{fields.reason}")

    return None
