"""Pure Autobazar.eu HTML / __NEXT_DATA__ extractors (no network, no PII persistence).

CZ vs SK policy
---------------
Default discover filter is ``location=200000000`` (Česká republika).
Slovak inventory (``100000000`` / parentNames containing Slovensko) is dropped
even if it leaks into a mixed page — Drivecheck comps stay CZ-first.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

from drivecheck_crawler.catalog.normalize import map_fuel
from drivecheck_crawler.fx import import_fx_fields, normalize_currency, to_czk
from drivecheck_crawler.normalize import (
    parse_datetime,
    parse_int,
    parse_money_amount,
    parse_year,
    strip_contact_text,
)

AUTOBAZAR_BASE = "https://www.autobazar.eu"
CZ_LOCATION_ID = "200000000"
SK_LOCATION_ID = "100000000"

# Known subjectType ids observed on list cards (dealer company vs private).
_SELLER_DEALER_TYPES = frozenset({30852})
_SELLER_PRIVATE_TYPES = frozenset({23348})

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.I | re.S,
)


def parse_next_data(html: str) -> dict[str, Any] | None:
    m = _NEXT_DATA_RE.search(html or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def page_props(html: str) -> dict[str, Any] | None:
    data = parse_next_data(html)
    if not data:
        return None
    props = data.get("props")
    if not isinstance(props, dict):
        return None
    pp = props.get("pageProps")
    return pp if isinstance(pp, dict) else None


def list_records_from_html(html: str) -> list[dict[str, Any]]:
    pp = page_props(html)
    if not pp:
        return []
    records = (pp.get("searchRecords") or {}).get("data")
    if not isinstance(records, list):
        return []
    return [r for r in records if isinstance(r, dict)]


def detail_record_from_html(html: str) -> dict[str, Any] | None:
    pp = page_props(html)
    if not pp:
        return None
    adv = pp.get("advertisement")
    return adv if isinstance(adv, dict) else None


def parse_max_list_page(html: str) -> int | None:
    pp = page_props(html)
    if not pp:
        return None
    raw = pp.get("maxPage")
    if isinstance(raw, int) and raw >= 1:
        return raw
    n = parse_int(raw)
    return n if n is not None and n >= 1 else None


def is_czech_location(record: dict[str, Any]) -> bool:
    """True when listing is located in Česká republika."""
    ids = record.get("locationIds")
    if isinstance(ids, list) and any(str(x) == CZ_LOCATION_ID for x in ids):
        return True
    loc = record.get("location")
    if not isinstance(loc, dict):
        return False
    parents = loc.get("parents")
    if isinstance(parents, list) and any(str(x) == CZ_LOCATION_ID for x in parents):
        return True
    names = loc.get("parentNames")
    if isinstance(names, list):
        joined = " ".join(str(n) for n in names).casefold()
        if "česká republika" in joined or "ceska republika" in joined:
            return True
        if "slovensko" in joined:
            return False
    return False


def region_from_record(record: dict[str, Any]) -> str | None:
    """Broad locality only — city or kraj; never street / zip / seller name."""
    loc = record.get("location")
    if not isinstance(loc, dict):
        return None
    name = loc.get("name")
    if name and str(name).strip():
        return str(name).strip()
    parents = loc.get("parentNames")
    if isinstance(parents, list):
        for item in parents:
            text = str(item).strip()
            if text and "republika" not in text.casefold() and "slovensko" not in text.casefold():
                return text
    return None


def seller_type_from_record(record: dict[str, Any]) -> str:
    raw = record.get("userSubjectType")
    if raw is None:
        user = record.get("user")
        if isinstance(user, dict):
            raw = user.get("subjectType")
    try:
        code = int(raw) if raw is not None else None
    except (TypeError, ValueError):
        code = None
    if code in _SELLER_DEALER_TYPES:
        return "dealer"
    if code in _SELLER_PRIVATE_TYPES:
        return "private"
    user = record.get("user")
    if isinstance(user, dict):
        auth = user.get("authorizedDealer")
        if isinstance(auth, dict) and auth.get("isAuthorized"):
            return "dealer"
        packages = user.get("packages")
        if isinstance(packages, dict) and any(
            packages.get(k)
            for k in (
                "hasBasicPackage",
                "hasCompactPackage",
                "hasComfortPackage",
                "hasPremiumPackage",
                "hasMasterPackage",
                "hasProfessionalPackage",
            )
        ):
            return "dealer"
    return "unknown"


def parse_mileage_km(raw: object) -> int | None:
    """Odometer km only — reject EV-range / dojezd phrasing if it ever appears."""
    if raw is None:
        return None
    if isinstance(raw, str) and re.search(r"dojezd|wltp|bater", raw, re.I):
        return None
    n = parse_int(raw)
    if n is None or n < 0 or n > 2_000_000:
        return None
    return n


def map_transmission(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.casefold()
    if "dsg" in s or "dvojspoj" in s:
        return "DSG"
    if "cvt" in s:
        return "CVT"
    if "aut" in s or "tiptronic" in s or "eat" in s or "pdk" in s:
        return "Automatická"
    if "man" in s:
        return "Manuální"
    return None


def map_drive(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.casefold()
    if "4x4" in s or "4wd" in s or "awd" in s or "quattro" in s or "xdrive" in s:
        return "4×4"
    if "přední" in s or "predni" in s or "fwd" in s:
        return "Přední"
    if "zadní" in s or "zadni" in s or "rwd" in s:
        return "Zadní"
    return None


def map_body(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.casefold()
    if "suv" in s or "off-road" in s or "terén" in s or "teren" in s:
        return "SUV"
    if "kombi" in s or "combi" in s or "touring" in s:
        return "Kombi"
    if "hatch" in s:
        return "Hatchback"
    if "sedan" in s or "limuz" in s:
        return "Sedan"
    if "coup" in s:
        return "Coupe"
    if "cabrio" in s or "roadster" in s:
        return "Cabrio"
    if "mpv" in s or "van" in s or "minivan" in s:
        return "MPV"
    if "pick" in s:
        return "Pick-up"
    return None


def map_fuel_value(raw: str | None) -> str | None:
    if not raw:
        return None
    mapped = map_fuel(raw)
    return None if mapped == "Neuvedeno" else mapped


def first_image_url(record: dict[str, Any]) -> str | None:
    from drivecheck_crawler.thumbs.urls import absolutize_image_url

    image = record.get("image")
    if isinstance(image, dict):
        previews = image.get("previewUrls")
        if isinstance(previews, dict):
            for key in ("record_preview", "record_premium", "orig", "record_premium_thumb"):
                url = absolutize_image_url(
                    previews.get(key) if isinstance(previews.get(key), str) else None
                )
                if url:
                    return url
        url = absolutize_image_url(
            image.get("url") if isinstance(image.get("url"), str) else None
        )
        if url:
            return url
    images = record.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            return first_image_url({"image": first})
        if isinstance(first, str):
            return absolutize_image_url(first)
    return None


def listing_url(record: dict[str, Any], *, lang: str = "cs") -> str | None:
    listing_id = str(record.get("id") or "").strip()
    sef = str(record.get("sefName") or "").strip().strip("/")
    if not listing_id:
        return None
    if sef:
        path = f"/{lang}/detail/{sef}/{listing_id}/"
    else:
        path = f"/{lang}/detail/{listing_id}/"
    return urljoin(AUTOBAZAR_BASE + "/", path.lstrip("/"))


def _record_currency_hint(record: dict[str, Any]) -> str | None:
    """Explicit listing currency only — not seller country.currency (often CZK)."""
    for key in (
        "currency",
        "priceCurrency",
        "currencyCode",
        "currency_code",
        "price_currency",
    ):
        raw = record.get(key)
        if raw is None or raw == "":
            continue
        code = normalize_currency(str(raw))
        if code in ("CZK", "EUR"):
            return code
    return None


def offer_price_amount(record: dict[str, Any]) -> tuple[float, str] | None:
    """Return ``(amount, currency)`` for an Autobazar list/detail record.

    Autobazar.eu quotes offers in **EUR** (UI shows €). Detail payloads sometimes
    expose fractional EUR (``finalPrice: 2270.98``) plus a CZK mirror in ``price``
    when ``unitPrice == 1``. Older code used :func:`parse_int` on those floats,
    turning ``2270.98`` into ``227098`` and then × FX (~5.7M CZK).

    Rules:
    - Prefer explicit CZK / EUR on the record when present.
    - ``unitPrice == 1`` + large ``price`` → native CZK (do **not** FX-multiply).
    - Otherwise treat ``finalPrice`` / ``priceCurrent`` / ``price`` as EUR when
      in a plausible EUR band; large bare amounts fall back to CZK.
    """
    hinted = _record_currency_hint(record)
    final = parse_money_amount(record.get("finalPrice"))
    current = parse_money_amount(record.get("priceCurrent"))
    price = parse_money_amount(record.get("price"))
    eur_candidate = final if final is not None else current

    try:
        unit = int(record["unitPrice"]) if record.get("unitPrice") is not None else 0
    except (TypeError, ValueError):
        unit = 0

    # Dual-currency detail: portal already provides CZK in `price`.
    if (
        unit == 1
        and price is not None
        and 5_000 <= price <= 50_000_000
        and (eur_candidate is None or price >= eur_candidate * 3)
    ):
        if hinted != "EUR":
            return price, "CZK"

    if hinted == "CZK":
        for amount in (price, final, current):
            if amount is not None and 5_000 <= amount <= 50_000_000:
                return amount, "CZK"
        return None

    if eur_candidate is not None and 500 <= eur_candidate <= 500_000:
        return eur_candidate, "EUR"

    if price is not None:
        if 500 <= price <= 500_000:
            return price, hinted or "EUR"
        if 5_000 <= price <= 50_000_000:
            return price, "CZK"
    return None


def offer_price_eur(record: dict[str, Any]) -> int | None:
    """Backward-compatible EUR whole-euro amount (None when offer is native CZK)."""
    parsed = offer_price_amount(record)
    if parsed is None:
        return None
    amount, currency = parsed
    if currency != "EUR":
        return None
    return int(round(amount))


def fields_from_record(
    record: dict[str, Any],
    *,
    require_czech: bool = True,
) -> dict[str, Any] | None:
    """Map Autobazar list/detail record → commercial fields (no PII / VIN).

    Intentionally ignores: vin, user.displayName / street / zip / telephone /
    email / username, description body (may contain contacts).
    """
    if require_czech and not is_czech_location(record):
        return None

    external_id = str(record.get("id") or "").strip()
    priced = offer_price_amount(record)
    if not external_id or priced is None:
        return None
    amount, currency = priced

    url = listing_url(record)
    if not url:
        return None

    try:
        # to_czk: native CZK stays whole koruny; EUR converts then nearest-100.
        price_czk = to_czk(amount, currency)
    except ValueError:
        return None
    if price_czk < 5_000 or price_czk > 50_000_000:
        return None

    title_raw = record.get("title")
    title = (
        strip_contact_text(str(title_raw)).strip() if title_raw else None
    ) or None
    make = str(record.get("brandValue") or "").strip() or None
    model = str(record.get("carModelValue") or "").strip() or None
    if make and make.casefold() == "skoda":
        make = "Škoda"

    year = parse_year(record.get("yearValue"))
    mileage = parse_mileage_km(record.get("mileage"))
    fuel = map_fuel_value(
        str(record.get("fuelValue") or "") or None
    )
    transmission = map_transmission(
        str(record.get("gearboxValue") or "") or None
    )
    drive = map_drive(str(record.get("driveValue") or "") or None)
    power_kw = parse_int(record.get("enginePower"))
    if power_kw is not None and not (20 <= power_kw <= 1500):
        power_kw = None
    displacement_cc = parse_int(record.get("engineCapacity"))
    if displacement_cc is not None and not (600 <= displacement_cc <= 10_000):
        displacement_cc = None
    body = map_body(str(record.get("bodyworkValue") or "") or None)

    published = parse_datetime(
        record.get("clientCreatedAt") or record.get("createdAt")
    )

    return {
        "external_id": external_id,
        "url": url,
        "make": make,
        "model": model,
        "year": year,
        "mileage_km": mileage,
        "fuel": fuel,
        "transmission": transmission,
        "drive": drive,
        "power_kw": power_kw,
        "displacement_cc": displacement_cc,
        "body": body,
        "seller_type": seller_type_from_record(record),
        "region": region_from_record(record),
        "price_czk": price_czk,
        "currency": currency,
        **import_fx_fields(amount, currency),
        "image_url": first_image_url(record),
        "title": title,
        "published_at": published,
    }


def merge_field_dicts(
    base: dict[str, Any], enrich: dict[str, Any]
) -> dict[str, Any]:
    out = dict(base)
    for key, value in enrich.items():
        if value is None or value == "":
            continue
        out[key] = value
    return out
