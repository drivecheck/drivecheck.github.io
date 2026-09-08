"""Pure AutoScout24.de HTML / __NEXT_DATA__ extractors (no network, no PII).

Market: autoscout24.de (German marketplace — common import comps for CZ dealers).
Search uses ``damaged_listing=exclude``; extract still drops ``isCurrentlyDamaged``.

Commercial fields only — never phone / email / street / seller name / VIN.
Prices are EUR → ``price_czk`` via FX (nearest 100 CZK) + ``currency=EUR``.
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

AS24_BASE = "https://www.autoscout24.de"

_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
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
    listings = pp.get("listings")
    if not isinstance(listings, list):
        return []
    return [x for x in listings if isinstance(x, dict)]


def parse_max_list_page(html: str) -> int | None:
    pp = page_props(html)
    if not pp:
        return None
    n = pp.get("numberOfPages")
    if isinstance(n, int) and n >= 1:
        return min(n, 200)
    try:
        return min(int(n), 200) if n is not None else None
    except (TypeError, ValueError):
        return None


def parse_mileage_km(raw: object) -> int | None:
    if isinstance(raw, int):
        return raw if 0 < raw < 2_000_000 else None
    text = str(raw or "")
    # Reject consumption-like "l/100 km"
    if re.search(r"l\s*/\s*100", text, re.I):
        return None
    digits = re.sub(r"[^\d]", "", text.split("km")[0] if "km" in text.casefold() else text)
    if not digits:
        return None
    n = int(digits)
    return n if 0 < n < 2_000_000 else None


def parse_power_kw(raw: object) -> int | None:
    if isinstance(raw, (int, float)):
        n = int(raw)
        return n if 15 <= n <= 800 else None
    text = str(raw or "")
    m = re.search(r"(\d+)\s*kW", text, re.I)
    if m:
        n = int(m.group(1))
        return n if 15 <= n <= 800 else None
    return None


def parse_displacement_cc(raw: object) -> int | None:
    if isinstance(raw, (int, float)):
        n = int(raw)
        return n if 500 <= n <= 10_000 else None
    text = str(raw or "")
    m = re.search(r"([\d.]+)\s*cm", text, re.I)
    if m:
        try:
            liters_or_cc = float(m.group(1).replace(",", "."))
        except ValueError:
            return None
        # "1.199 cm³" → 1199
        if liters_or_cc < 20:
            n = int(round(liters_or_cc * 1000))
        else:
            n = int(round(liters_or_cc))
        return n if 500 <= n <= 10_000 else None
    return None


def year_from_vehicle_details(details: object) -> int | None:
    if not isinstance(details, list):
        return None
    for item in details:
        if not isinstance(item, dict):
            continue
        icon = str(item.get("iconName") or "")
        aria = str(item.get("ariaLabel") or "")
        data = item.get("data")
        if "calendar" in icon or "Erstzulassung" in aria or "registration" in aria.casefold():
            y = parse_year(data)
            if y:
                return y
            text = str(data or "")
            m = re.search(r"(19|20)\d{2}", text)
            if m:
                return int(m.group(0))
    return None


def listing_url(record: dict[str, Any]) -> str | None:
    path = record.get("url")
    if isinstance(path, str) and path.strip():
        p = path.strip()
        if p.startswith("http"):
            return p.split("?")[0]
        if p.startswith("/"):
            return AS24_BASE + p.split("?")[0]
    return None


def external_id_from_record(record: dict[str, Any]) -> str | None:
    ident = record.get("identifier")
    if isinstance(ident, dict):
        xref = ident.get("crossReferenceId") or ident.get("legacyId")
        if xref:
            return str(xref).strip()
    xref = record.get("crossReferenceId")
    if xref:
        return str(xref).strip()
    rid = record.get("id")
    if rid:
        return str(rid).strip()
    return None


def _feature_names(vehicle: dict[str, Any]) -> list[str]:
    out: list[str] = []
    sub = vehicle.get("subtitle")
    if isinstance(sub, str) and sub.strip():
        # Comma-separated equipment blurb on AS24 cards
        out.extend(p.strip() for p in sub.split(",") if p.strip())
    return out


def fields_from_record(record: dict[str, Any]) -> dict[str, Any] | None:
    vehicle = record.get("vehicle")
    if not isinstance(vehicle, dict):
        return None

    external_id = external_id_from_record(record)
    url = listing_url(record)
    price_obj = record.get("price") if isinstance(record.get("price"), dict) else {}
    price_eur = parse_int(price_obj.get("priceRaw"))
    if not external_id or not url or price_eur is None:
        return None
    if price_eur < 300 or price_eur > 500_000:
        return None

    title_bits = [
        str(vehicle.get("make") or ""),
        str(vehicle.get("model") or ""),
        str(vehicle.get("modelVersionInput") or vehicle.get("variant") or ""),
    ]
    title_raw = " ".join(b for b in title_bits if b).strip() or None
    title = strip_contact_text(title_raw) if title_raw else None

    flags = {
        "isCurrentlyDamaged": vehicle.get("isCurrentlyDamaged"),
        "accidentDamaged": vehicle.get("accidentDamaged"),
    }
    special = record.get("specialConditions")
    text_blobs = [
        title,
        str(vehicle.get("subtitle") or ""),
        str(vehicle.get("modelVersionInput") or ""),
    ]
    if should_skip_accident_listing(
        title=title,
        text_blobs=text_blobs,
        flags=flags,
        special_conditions=special,
    ):
        return None

    try:
        price_czk = to_czk(price_eur, "EUR")
    except ValueError:
        return None
    if price_czk < 5_000 or price_czk > 50_000_000:
        return None

    make = map_de_make(str(vehicle.get("make") or "") or None)
    model = str(vehicle.get("model") or vehicle.get("modelGroup") or "").strip() or None
    year = year_from_vehicle_details(record.get("vehicleDetails")) or parse_year(
        vehicle.get("firstRegistration")
    )
    mileage = parse_mileage_km(vehicle.get("mileageInKm"))
    fuel = map_de_fuel(str(vehicle.get("fuel") or "") or None)
    transmission = map_de_transmission(str(vehicle.get("transmission") or "") or None)
    drive = map_de_drive(str(vehicle.get("drive") or vehicle.get("driveTrain") or "") or None)
    body = map_de_body(str(vehicle.get("bodyType") or vehicle.get("body") or "") or None)
    power_kw = None
    displacement_cc = parse_displacement_cc(vehicle.get("engineDisplacementInCCM"))
    details = record.get("vehicleDetails")
    if isinstance(details, list):
        for item in details:
            if not isinstance(item, dict):
                continue
            icon = str(item.get("iconName") or "")
            if "speedometer" in icon or "Leistung" in str(item.get("ariaLabel") or ""):
                power_kw = parse_power_kw(item.get("data")) or power_kw

    seller = record.get("seller") if isinstance(record.get("seller"), dict) else {}
    seller_type = "dealer" if str(seller.get("type") or "").lower() == "dealer" else (
        "private" if str(seller.get("type") or "").lower() == "private" else "unknown"
    )

    loc = record.get("location") if isinstance(record.get("location"), dict) else {}
    # City only — never street / zip as PII-adjacent detail
    region = str(loc.get("city") or "").strip() or None

    images = record.get("images") if isinstance(record.get("images"), list) else []
    image_url = None
    if images and isinstance(images[0], str):
        from drivecheck_crawler.thumbs.urls import absolutize_image_url

        image_url = absolutize_image_url(images[0])

    feature_keys = normalize_known_feature_list(_feature_names(vehicle))

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
        "seller_type": seller_type,
        "region": region,
        "price_czk": price_czk,
        "currency": "EUR",
        **import_fx_fields(price_eur, "EUR"),
        "feature_keys": feature_keys,
        "image_url": image_url,
        "title": title,
    }
