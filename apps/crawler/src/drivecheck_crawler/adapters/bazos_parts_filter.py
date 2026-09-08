"""Precision-first Bazos filter: reject car-parts ads, keep whole vehicles.

Decisions prefer title (+ first line of description) over deep body text so
service-history mentions ("vyměněny rozvody") do not look like parts sales.
When unsure but a concrete parts-intent signal is present → reject.

Matching runs on accent-folded lowercase text (ě→e, ř→r, …).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


# Supporting signal only — never reject on price alone.
_LOW_PARTS_PRICE_CZK = 20_000

# Typical passenger-car asking prices on CZ marketplaces.
_CAR_PRICE_MIN_CZK = 25_000
_CAR_PRICE_MAX_CZK = 5_000_000


@dataclass(frozen=True, slots=True)
class PartsReject:
    reason: str


def _fold(text: str) -> str:
    """Lowercase + strip combining marks for accent-insensitive matching."""
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
    """Title + first description line — primary reject surface."""
    t = (title or "").strip()
    head = _first_line(popis)
    if not head:
        return t
    if not t:
        return head
    return f"{t}\n{head}"


# Whole-car keep language (service / ownership) on folded text.
_KEEP_SERVICE = re.compile(
    r"(?:"
    r"\bvymen[eany]\w*\b"
    r"|\bvymena\b"
    r"|\bnov[aey]\s+(?:rozvody|spojk|brzd|tlumi|olej|pneumatik|pneu|disky|kola)\b"
    r"|\brozvody\b"
    r"|\brozvodov\w*"
    r"|\bspojk[ay]\b"
    r"|\bservisn\w*\s+kni[z]\w*"
    r"|\bserviska\b"
    r"|\bfull\s*servis\b"
    r"|\bregularne\s+servis"
    r"|\bstk\b"
    r"|\bnajeto\b"
    r"|\bnajezd\b"
    r"|\btachometr\b"
    r"|\b1\.\s*majitel\b"
    r"|\bprvni\s+majitel\b"
    r"|\bbez\s+nehody\b"
    r"|\bnebourane\b"
    r")"
)

# Title reads as selling a whole car (not a spare).
_VEHICLE_SALE_TITLE = re.compile(
    r"(?:"
    r"\bprodam\b"
    r"|\bprodavam\b"
    r"|\bauto\s+na\s+prodej\b"
    r"|\bna\s+prodej\b"
    r"|\bcombi\b"
    r"|\bkombi\b"
    r"|\bsedan\b"
    r"|\bhatchback\b"
    r"|\bsuv\b"
    r"|\bcoupe\b"
    r"|\bkabriolet\b"
    r"|\blimuzina\b"
    r"|\b\d\.\d\s*(?:tsi|tdi|tfsi|hdi|dci|cdi|gdi|mpi)\b"
    r"|\b\d{2,3}\s*kw\b"
    r"|\b\d{1,3}\s*tis\.?\s*km\b"
    r"|\b\d{4,7}\s*km\b"
    r"|\br\.?\s*v\.?\b"
    r"|\brv\s*\d{4}\b"
    r"|\b20[0-2]\d\b"
    r"|\b199\d\b"
    r")"
)

# Strong parts / wreck / dismantling intent (title / headline).
_STRONG_PARTS: list[tuple[str, re.Pattern[str]]] = [
    (
        "nahradni_dily_phrase",
        re.compile(
            r"(?:"
            r"\bnahradni\s+dily\b"
            r"|\bdily\s+na\s+"
            r"|\bbazar\s+dil"
            r"|\bautodily\b"
            r"|\bautodilna\b"
            r"|\bna\s+nahradni\s+dily\b"
            r"|\bna\s+dily\b"
            r")"
        ),
    ),
    (
        "rozborka_vrak",
        re.compile(
            r"(?:"
            r"\brozborka\b"
            r"|\brozebirka\b"
            r"|\bvrakovan"
            r"|\bvrakovist"
            r"|\bvrak\b"
            r"|\bautovrak\b"
            r"|\bdemontaz"
            r")"
        ),
    ),
    (
        "sell_major_unit",
        re.compile(
            r"(?:"
            r"\b(?:prodam|prodavam|nabizim|prodej)\s+"
            r"(?:kompletni\s+)?"
            r"(?:motor|prevodovk|motorov\w*\s+hlav|turbo|turbodmychad|"
            r"diferencial|naprava|poloos|vstrikovac|alternator|starter|"
            r"katalyzator|vyfuk|chladic|kompresor)\b"
            r"|\bmotor\s+na\s+"
            r"|\bprevodovk[ay]\s+na\s+"
            r"|\bmotor\s+(?:1[.,]\d|2[.,]\d|tdi|tsi|hdi|dci|cdi)\b"
            r")"
        ),
    ),
    (
        "body_panel_part",
        re.compile(
            r"(?:"
            r"\b(?:prodam|prodavam|nabizim|prodej)\s+"
            r"(?:predni\s+|zadni\s+|leve\s+|prav[e]\s+|l\.\s*|p\.\s*)?"
            r"(?:kapot|naraznik|blatnik|dvere|"
            r"zrcatko|svetlomet|mask[ayu]|kufr(?:ove)?\s+viko|"
            r"bocni\s+sklo|celni\s+sklo|strecha)\b"
            r"|\b(?:kapota|naraznik|blatnik)\s+na\s+"
            r"|\b(?:svetlomet|zrcatko)s?\s+na\s+"
            r"|\bdvere\s+na\s+"
            r")"
        ),
    ),
    (
        "wheels_tires_main",
        re.compile(
            r"(?:"
            r"\b(?:prodam|prodavam|nabizim|prodej)\s+"
            r"(?:sad[ayu]\s+)?"
            r"(?:kol|disky|disk[u]|pneu|pneumatik|alu\s*kola|lita\s*kola|"
            r"zimni\s+kola|letni\s+kola|zimni\s+pneu|letni\s+pneu)\b"
            r"|\bsada\s+(?:kol|disku|pneu|pneumatik)\b"
            r"|\b\d{2,3}\s*/\s*\d{2,3}\s*r\d{2}\b"
            r")"
        ),
    ),
    (
        "interior_electronics_part",
        re.compile(
            r"(?:"
            r"\b(?:prodam|prodavam|nabizim|prodej)\s+"
            r"(?:predni\s+|zadni\s+)?"
            r"(?:sedack\w*|palubni\s+desk\w*|"
            r"volant|radi[oa]|navigaci|navigace|display|displej|"
            r"ridici\s+jednotk\w*|abs\s+jednotk\w*|"
            r"generator|alternator)\b"
            r")"
        ),
    ),
]

# Weaker title cues — only reject with low price or without vehicle-sale cues.
_WEAK_PARTS = re.compile(
    r"(?:"
    r"\bdil\b"
    r"|\bdily\b"
    r"|\bnahradn"
    r"|\bmotor\b"
    r"|\bprevodovk"
    r"|\bkapot"
    r"|\bnarazn"
    r"|\bzrcatk"
    r"|\bsvetlomet"
    r"|\bblatnik"
    r"|\bturbo\b"
    r"|\bpoloos"
    r"|\bnaprav[ay]\b"
    r")"
)

# Bare "díl/díly" in a clear service context on the headline → not weak parts.
_WEAK_IN_SERVICE = re.compile(
    r"(?:"
    r"vymen\w*\s+(?:\w+\s+){0,3}(?:dil|dily|motor|spojk|rozvod|brzd|tlumi)"
    r"|(?:dil|dily)\s+vymen"
    r"|\bnov[e]\s+(?:dily|rozvody|spojky)\b"
    r"|\boriginalni\s+dily\b"
    r")"
)


def _has_strong_parts(folded_headline: str) -> str | None:
    for reason, pattern in _STRONG_PARTS:
        if pattern.search(folded_headline):
            return reason
    return None


def _looks_like_vehicle_sale(folded_title: str, price_czk: int | None) -> bool:
    if not _VEHICLE_SALE_TITLE.search(folded_title):
        return False
    if price_czk is not None and not (_CAR_PRICE_MIN_CZK <= price_czk <= _CAR_PRICE_MAX_CZK):
        return False
    return True


def should_reject_as_parts(
    title: str | None,
    popis: str | None = None,
    price_czk: int | None = None,
    *,
    url: str | None = None,
) -> PartsReject | None:
    """Return reject reason when listing is likely parts/wreck, else None.

    ``url`` is accepted for call-site convenience and currently unused.
    """
    _ = url
    headline = _headline(title, popis)
    if not headline.strip():
        return None

    folded_headline = _fold(headline)
    folded_title = _fold(title or "")

    strong = _has_strong_parts(folded_headline)
    if strong:
        return PartsReject(reason=strong)

    if _KEEP_SERVICE.search(folded_headline) and _looks_like_vehicle_sale(
        folded_title, price_czk
    ):
        return None

    if _looks_like_vehicle_sale(folded_title, price_czk) and not _WEAK_PARTS.search(
        folded_title
    ):
        return None

    weak_hit = _WEAK_PARTS.search(folded_title) or _WEAK_PARTS.search(folded_headline)
    if weak_hit:
        if _WEAK_IN_SERVICE.search(folded_headline):
            return None
        if _looks_like_vehicle_sale(folded_title, price_czk) and (
            price_czk is None or price_czk >= _CAR_PRICE_MIN_CZK
        ):
            return None
        if price_czk is not None and price_czk < _LOW_PARTS_PRICE_CZK:
            return PartsReject(reason=f"weak_parts_low_price:{weak_hit.group(0)}")
        if not _looks_like_vehicle_sale(folded_title, price_czk):
            return PartsReject(reason=f"weak_parts_title:{weak_hit.group(0)}")

    return None


def is_likely_vehicle_listing(
    title: str | None,
    popis: str | None = None,
    price_czk: int | None = None,
    *,
    url: str | None = None,
) -> bool:
    return should_reject_as_parts(title, popis, price_czk, url=url) is None
