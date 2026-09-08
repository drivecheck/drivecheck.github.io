"""Pure Mobile.de HTML / __NEXT_DATA__ extractors (no network, no PII).

Spike note (2026-08-06/07): live ``suchen.mobile.de`` returns hard Akamai
HTTP 403 "Zugriff verweigert / Access denied" from typical CZ/DC IPs (not a
JS challenge). Use ``MOBILE_DE_HTTP_PROXY`` for unblocked egress. Adapter +
fixtures are wired for when polite fetch succeeds; discover logs WAF and
stops the batch (no fake rows).

Search prefers ``dam=0`` (exclude damaged). Extract also drops accident flags
and Unfall-/Bastler- titles.

Commercial fields only — never phone / email / street / seller name / VIN.
EUR → ``price_czk`` via FX (nearest 100 CZK) + ``currency=EUR``.
"""

from __future__ import annotations

import json
import re
from typing import Any

from drivecheck_crawler.accident import should_skip_accident_listing
from drivecheck_crawler.adapters.de_normalize import (
    map_de_body,
    map_de_drive,
    map_de_fuel,
    map_de_make,
    map_de_transmission,
)
from drivecheck_crawler.features import normalize_known_feature_list
from drivecheck_crawler.fx import import_fx_fields, to_czk
from drivecheck_crawler.normalize import parse_int, parse_year, strip_contact_text

MOBILE_BASE = "https://suchen.mobile.de"

_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)

_FUEL_ENUM = {
    "diesel": "Nafta",
    "petrol": "Benzín",
    "gasoline": "Benzín",
    "benzin": "Benzín",
    "electric": "Elektro",
    "elektro": "Elektro",
    "hybrid": "Hybrid",
    "plugin_hybrid": "Hybrid",
    "lpg": "LPG",
    "cng": "CNG",
    "hydrogen": "Vodík",
}

_GEAR_ENUM = {
    "manual_gear": "Manuální",
    "manual": "Manuální",
    "automatic_gear": "Automatická",
    "automatic": "Automatická",
    "semi_automatic": "Automatická",
}

_BODY_ENUM = {
    "estatecar": "Kombi",
    "estate": "Kombi",
    "limousine": "Sedan",
    "smallcar": "Hatchback",
    "suv": "SUV",
    "offroad": "SUV",
    "van": "MPV",
    "cabrio": "Cabrio",
    "sportsCar": "Coupe",
    "sportscar": "Coupe",
    "other": None,
}


def parse_next_data(html: str) -> dict[str, Any] | None:
    m = _NEXT_DATA_RE.search(html or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def search_results(html: str) -> dict[str, Any] | None:
    data = parse_next_data(html)
    if not data:
        return None
    props = data.get("props")
    if not isinstance(props, dict):
        return None
    pp = props.get("pageProps")
    if not isinstance(pp, dict):
        return None
    sr = pp.get("searchResults")
    return sr if isinstance(sr, dict) else None


def list_records_from_html(html: str) -> list[dict[str, Any]]:
    sr = search_results(html)
    if not sr:
        return []
    items = sr.get("items")
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]


def parse_max_list_page(html: str) -> int | None:
    sr = search_results(html)
    if not sr:
        return None
    for key in ("maxPages", "numPages", "totalPages"):
        n = sr.get(key)
        if isinstance(n, int) and n >= 1:
            return min(n, 50)
        try:
            if n is not None:
                return min(int(n), 50)
        except (TypeError, ValueError):
            continue
    total = sr.get("numResultsTotal")
    page_size = sr.get("pageSize") or 20
    try:
        t = int(total)
        ps = int(page_size) or 20
        if t > 0 and ps > 0:
            return min((t + ps - 1) // ps, 50)
    except (TypeError, ValueError):
        pass
    return None


def listing_url(record: dict[str, Any]) -> str | None:
    url = record.get("url")
    if isinstance(url, str) and url.startswith("http"):
        return url.split("#")[0]
    rel = record.get("relativeUrl") or record.get("relativePath")
    if isinstance(rel, str) and rel.strip():
        path = rel.strip()
        if path.startswith("http"):
            return path.split("#")[0]
        if not path.startswith("/"):
            path = "/" + path
        return MOBILE_BASE + path.split("#")[0]
    rid = record.get("id")
    if rid:
        return f"{MOBILE_BASE}/fahrzeuge/details.html?id={rid}"
    return None


def _map_fuel(raw: object) -> str | None:
    if raw is None:
        return None
    key = str(raw).strip().lower().replace("-", "_")
    if key in _FUEL_ENUM:
        return _FUEL_ENUM[key]
    return map_de_fuel(str(raw))


def _map_transmission(raw: object) -> str | None:
    if raw is None:
        return None
    key = str(raw).strip().lower().replace("-", "_")
    if key in _GEAR_ENUM:
        return _GEAR_ENUM[key]
    return map_de_transmission(str(raw).replace("_", " "))


def _map_body(raw: object) -> str | None:
    if raw is None:
        return None
    key = str(raw).strip().lower().replace("-", "").replace("_", "")
    if key in _BODY_ENUM:
        return _BODY_ENUM[key]
    return map_de_body(str(raw))


def fields_from_record(record: dict[str, Any]) -> dict[str, Any] | None:
    external_id = str(record.get("id") or "").strip()
    price_obj = record.get("price") if isinstance(record.get("price"), dict) else {}
    price_eur = parse_int(price_obj.get("gross") or price_obj.get("price") or price_obj.get("amount"))
    url = listing_url(record)
    if not external_id or not url or price_eur is None:
        return None
    if price_eur < 500 or price_eur > 500_000:
        return None

    title_raw = record.get("title")
    title = strip_contact_text(str(title_raw)).strip() if title_raw else None

    flags = {
        "isAccidentDamaged": record.get("isAccidentDamaged"),
        "accidentDamaged": record.get("accidentDamaged"),
        "damageUnrepaired": record.get("damageUnrepaired"),
        "isCurrentlyDamaged": record.get("isCurrentlyDamaged"),
        "unfallwagen": record.get("unfallwagen"),
    }
    if should_skip_accident_listing(
        title=title,
        text_blobs=[title, str(record.get("make") or ""), str(record.get("model") or "")],
        flags=flags,
        special_conditions=record.get("specialConditions") or record.get("tags"),
    ):
        return None

    try:
        price_czk = to_czk(price_eur, "EUR")
    except ValueError:
        return None
    if price_czk < 5_000 or price_czk > 50_000_000:
        return None

    make = map_de_make(str(record.get("make") or "") or None)
    model = str(record.get("model") or "").strip() or None
    year = parse_year(record.get("firstRegistration") or record.get("firstRegistrationDate"))
    mileage = parse_int(record.get("mileage") or record.get("mileageInKm"))
    if mileage is not None and not (0 < mileage < 2_000_000):
        mileage = None
    fuel = _map_fuel(record.get("fuel") or record.get("fuelType"))
    transmission = _map_transmission(record.get("transmission") or record.get("gearbox"))
    drive = map_de_drive(str(record.get("drive") or record.get("driveTrain") or "") or None)
    body = _map_body(record.get("category") or record.get("bodyType") or record.get("body"))
    power_kw = parse_int(record.get("power") or record.get("powerKw"))
    if power_kw is not None and not (15 <= power_kw <= 800):
        power_kw = None

    contact = record.get("contact") if isinstance(record.get("contact"), dict) else {}
    ctype = str(contact.get("type") or record.get("sellerType") or "").upper()
    if "DEALER" in ctype or "HAENDLER" in ctype or "HÄNDLER" in ctype:
        seller_type = "dealer"
    elif "PRIVATE" in ctype or "PRIVAT" in ctype:
        seller_type = "private"
    else:
        seller_type = "unknown"

    attr = record.get("attr") if isinstance(record.get("attr"), dict) else {}
    region = str(attr.get("cn") or attr.get("city") or record.get("city") or "").strip() or None

    images = record.get("images") if isinstance(record.get("images"), list) else []
    image_url = None
    if images:
        from drivecheck_crawler.thumbs.urls import absolutize_image_url

        first = images[0]
        if isinstance(first, str):
            image_url = absolutize_image_url(first)
        elif isinstance(first, dict):
            uri = first.get("uri") or first.get("url")
            if isinstance(uri, str):
                image_url = absolutize_image_url(uri)

    feat_raw = record.get("features") or record.get("equipment") or []
    feat_names: list[str] = []
    if isinstance(feat_raw, list):
        for item in feat_raw:
            if isinstance(item, str):
                feat_names.append(item)
            elif isinstance(item, dict):
                label = item.get("label") or item.get("name") or item.get("id")
                if label:
                    feat_names.append(str(label))
    feature_keys = normalize_known_feature_list(feat_names)

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
        "body": body,
        "seller_type": seller_type,
        "region": region,
        "price_czk": price_czk,
        "currency": "EUR",
        **import_fx_fields(price_eur, "EUR"),
        "feature_keys": feature_keys,
        "image_url": image_url,
        "title": title,
    }
