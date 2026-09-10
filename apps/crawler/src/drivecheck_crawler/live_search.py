from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from drivecheck_crawler.adapters.bazos import BAZOS_BASE, BRAND_LABELS
from drivecheck_crawler.adapters.sauto import CATEGORY_OSOBNI, SAUTO_REFERER, SAUTO_SEARCH, _first_image_url
from drivecheck_crawler.config import get_config
from drivecheck_crawler.http_client import RateLimitedClient
from drivecheck_crawler.listing_quality import should_reject_listing
from drivecheck_crawler.normalize import (
    cb_name,
    map_seller_type,
    parse_int,
    parse_price_czk,
    parse_year,
)

log = logging.getLogger(__name__)

BAZOS_SLUG = {
    "škoda": "skoda",
    "skoda": "skoda",
    "volkswagen": "volkswagen",
    "vw": "volkswagen",
    "mercedes-benz": "mercedes",
    "mercedes": "mercedes",
    "alfa romeo": "alfa",
    "bmw": "bmw",
    "audi": "audi",
    "ford": "ford",
    "hyundai": "hyundai",
    "kia": "kia",
    "toyota": "toyota",
    "renault": "renault",
    "peugeot": "peugeot",
    "citroën": "citroen",
    "citroen": "citroen",
    "opel": "opel",
    "seat": "seat",
    "nissan": "nissan",
    "mazda": "mazda",
    "honda": "honda",
    "volvo": "volvo",
    "fiat": "fiat",
    "dacia": "dacia",
    "suzuki": "suzuki",
    "mitsubishi": "mitsubishi",
}


def _slug(value: str) -> str:
    text = value.strip().lower()
    return BAZOS_SLUG.get(text, re.sub(r"[^a-z0-9]+", "", text))


def dto_to_offer(dto_like: dict[str, Any], *, origin: str = "live") -> dict[str, Any]:
    return {
        "source": dto_like.get("source"),
        "externalId": str(dto_like.get("external_id") or dto_like.get("externalId") or ""),
        "url": dto_like.get("url"),
        "imageUrl": dto_like.get("image_url") or dto_like.get("imageUrl"),
        "title": dto_like.get("title"),
        "make": dto_like.get("make"),
        "model": dto_like.get("model"),
        "year": dto_like.get("year"),
        "mileageKm": dto_like.get("mileage_km") or dto_like.get("mileageKm"),
        "priceCzk": dto_like.get("price_czk") or dto_like.get("priceCzk"),
        "currency": dto_like.get("currency"),
        "priceForeign": dto_like.get("price_foreign") or dto_like.get("priceForeign"),
        "fxRateDate": dto_like.get("fx_rate_date") or dto_like.get("fxRateDate"),
        "fuel": dto_like.get("fuel"),
        "transmission": dto_like.get("transmission"),
        "sellerType": dto_like.get("seller_type") or dto_like.get("sellerType"),
        "region": dto_like.get("region"),
        "featureKeys": dto_like.get("feature_keys") or dto_like.get("featureKeys") or [],
        "publishedAt": None,
        "origin": origin,
    }


def _norm_token(value: str) -> str:
    text = value.strip().lower()
    # Strip common Czech diacritics for title matching.
    table = str.maketrans(
        "áäčďéěíľĺňóôŕšťúůýž",
        "aacdeeillnoorstuuyz",
    )
    return text.translate(table)


def _title_matches_model(title: str, model: str) -> bool:
    title_n = _norm_token(title)
    model_n = _norm_token(model)
    if not model_n:
        return False
    if model_n in title_n:
        return True
    parts = [p for p in re.split(r"[\s/-]+", model_n) if len(p) >= 2]
    if len(parts) <= 1:
        return False
    return all(p in title_n for p in parts)


def _fuel_key(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    s = _norm_token(str(raw))
    if s in {"neuvedeno", "neznamo", "unknown", "-"}:
        return None
    if "elektro" in s or "electric" in s or "bev" in s:
        return "elektro"
    if "hybrid" in s or "phev" in s:
        return "hybrid"
    if "lpg" in s and ("benzin" in s or "ba" in s):
        return "benzin+lpg"
    if "lpg" in s:
        return "lpg"
    if "cng" in s:
        return "cng"
    if "nafta" in s or "diesel" in s or s == "nm":
        return "nafta"
    if "benzin" in s or "petrol" in s or "gasoline" in s or "ba" in s:
        return "benzin"
    return s or None


def _transmission_key(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    s = _norm_token(str(raw))
    if s in {"neuvedeno", "neznamo", "unknown", "-"}:
        return None
    if "dsg" in s or "dvojspoj" in s or "dct" in s:
        return "dsg"
    if "cvt" in s:
        return "cvt"
    if "auto" in s or "automat" in s:
        return "automatic"
    if "manu" in s or s == "mt":
        return "manual"
    return None


def _transmission_compatible(want: str | None, have: str | None) -> bool:
    if not want or not have:
        return True
    if want == have:
        return True
    if want == "automatic" and have in {"dsg", "cvt", "automatic"}:
        return True
    if want == "dsg" and have in {"dsg", "automatic"}:
        return True
    if want == "cvt" and have in {"cvt", "automatic"}:
        return True
    return False


def _row_matches_vehicle(
    *,
    make_name: str | None,
    model_name: str | None,
    title: str,
    want_make: str,
    want_model: str,
    fuel: str | None = None,
    transmission: str | None = None,
    want_fuel: str | None = None,
    want_transmission: str | None = None,
) -> bool:
    make_n = _norm_token(want_make)
    model_n = _norm_token(want_model)
    if not make_n or not model_n:
        return False
    make_field = _norm_token(make_name or "")
    model_field = _norm_token(model_name or "")
    title_n = _norm_token(title)
    make_ok = make_n in make_field or make_n in title_n
    if not make_ok:
        return False
    # Title is authoritative when present (prevents stamped false model fields).
    if title_n:
        if not _title_matches_model(title, want_model):
            return False
    elif not (model_n in model_field or _title_matches_model(model_field, want_model)):
        return False

    # Hard dims: contradict → exclude; unknown listing field → allow (web ranks lower).
    want_f = _fuel_key(want_fuel)
    have_f = _fuel_key(fuel)
    if want_f and have_f and want_f != have_f:
        return False
    want_t = _transmission_key(want_transmission)
    have_t = _transmission_key(transmission)
    if want_t and have_t and not _transmission_compatible(want_t, have_t):
        return False
    return True


def search_sauto(
    client: RateLimitedClient,
    *,
    make: str,
    model: str,
    year: int | None,
    limit: int,
    fuel: str | None = None,
    transmission: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "limit": min(limit, 40),
        "offset": 0,
        "condition_seo": "ojete",
        "category_id": CATEGORY_OSOBNI,
        "operating_lease": "false",
        "query": f"{make} {model}".strip(),
    }
    if year:
        params["year_from"] = max(1990, year - 2)
        params["year_to"] = year + 2

    try:
        payload = client.get_json(SAUTO_SEARCH, params=params, referer=SAUTO_REFERER)
    except Exception as exc:
        log.warning("sauto live search failed: %s", exc)
        return []

    offers: list[dict[str, Any]] = []
    for row in payload.get("results") or []:
        item_id = row.get("id")
        price = parse_price_czk(row.get("price"))
        if item_id is None or price is None:
            continue
        manufacturer = row.get("manufacturer_cb") or {}
        model_cb = row.get("model_cb") or {}
        make_name = cb_name(manufacturer)
        model_name = cb_name(model_cb)
        title = f"{make_name or ''} {model_name or ''}".strip()
        row_fuel = cb_name(row.get("fuel_cb"))
        row_transmission = cb_name(row.get("gearbox_cb"))
        if not _row_matches_vehicle(
            make_name=make_name,
            model_name=model_name,
            title=title,
            want_make=make,
            want_model=model,
            fuel=row_fuel,
            transmission=row_transmission,
            want_fuel=fuel,
            want_transmission=transmission,
        ):
            continue
        make_seo = manufacturer.get("seo_name") or "auto"
        model_seo = model_cb.get("seo_name") or "model"
        url = (
            f"https://www.sauto.cz/osobni/detail/"
            f"{quote(str(make_seo))}/{quote(str(model_seo))}/{item_id}"
        )
        locality = row.get("locality") or {}
        y = parse_year(row.get("manufacturing_date")) or parse_year(row.get("in_operation_date"))
        offers.append(
            dto_to_offer(
                {
                    "source": "sauto",
                    "external_id": str(item_id),
                    "url": url,
                    "make": make_name,
                    "model": model_name,
                    "year": y,
                    "mileage_km": parse_int(row.get("tachometer")),
                    "fuel": row_fuel,
                    "transmission": row_transmission,
                    "seller_type": map_seller_type(premise=row.get("premise")),
                    "region": locality.get("region") or locality.get("district"),
                    "price_czk": price,
                    "image_url": _first_image_url(row),
                    "title": title,
                    "feature_keys": [],
                }
            )
        )
        if len(offers) >= limit:
            break
    return offers


def search_bazos(
    client: RateLimitedClient,
    *,
    make: str,
    model: str,
    limit: int,
) -> list[dict[str, Any]]:
    brand = _slug(make) or "ostatni"
    # Prefer search URL with model query when available; fall back to brand list.
    q = quote(f"{make} {model}".strip())
    list_url = f"{BAZOS_BASE}/{brand}/?hledat={q}"
    try:
        html = client.get_text(list_url, referer=BAZOS_BASE)
    except Exception as exc:
        log.warning("bazos live search failed: %s", exc)
        return []

    soup = BeautifulSoup(html, "lxml")
    offers: list[dict[str, Any]] = []

    for block in soup.select(".inzeraty, .inzerat, tr"):
        a = block.select_one('a[href*="/inzerat/"]')
        if not a:
            continue
        href = a.get("href") or ""
        m = re.search(r"/inzerat/(\d+)/", href)
        if not m:
            continue
        title = a.get_text(" ", strip=True)
        # Never pad with brand-only / unrelated models — that caused "random" live cars.
        if not _title_matches_model(title, model):
            continue
        price_el = block.select_one(".inzeratycena, .cena")
        price = parse_price_czk(price_el.get_text(" ", strip=True) if price_el else block.get_text(" ", strip=True))
        if price is None:
            continue
        detail_url = urljoin(BAZOS_BASE, href).split("?")[0]
        parts_reject = should_reject_listing(title=title, price_czk=price, url=detail_url)
        if parts_reject is not None:
            log.debug(
                "bazos live skip parts id=%s reason=%s title=%r",
                m.group(1),
                parts_reject.reason,
                title[:80],
            )
            continue
        img = block.select_one("img")
        image_url = None
        if img and img.get("src"):
            src = img["src"]
            if src.startswith("//"):
                src = "https:" + src
            if src.startswith("http"):
                image_url = src
        year = None
        ym = re.search(r"\b(19\d{2}|20[0-2]\d)\b", title)
        if ym:
            year = int(ym.group(1))
        offers.append(
            dto_to_offer(
                {
                    "source": "bazos",
                    "external_id": m.group(1),
                    "url": detail_url,
                    "make": BRAND_LABELS.get(brand, make),
                    "model": model,
                    "year": year,
                    "mileage_km": None,
                    "price_czk": price,
                    "image_url": image_url,
                    "title": title,
                    "seller_type": "unknown",
                    "feature_keys": [],
                }
            )
        )
        if len(offers) >= limit:
            break
    return offers


def run_live_search(
    *,
    make: str,
    model: str,
    year: int | None = None,
    limit: int = 40,
    sources: list[str] | None = None,
    fuel: str | None = None,
    transmission: str | None = None,
) -> list[dict[str, Any]]:
    cfg = get_config()
    wanted = set(sources or ["sauto", "bazos"])
    per = max(5, limit // max(1, len(wanted)))
    out: list[dict[str, Any]] = []
    with RateLimitedClient(cfg) as client:
        if "sauto" in wanted:
            out.extend(
                search_sauto(
                    client,
                    make=make,
                    model=model,
                    year=year,
                    limit=per,
                    fuel=fuel,
                    transmission=transmission,
                )
            )
        if "bazos" in wanted:
            # Bazos list cards usually lack fuel/transmission — model/title only here;
            # web matcher applies hard dims when fields are present after merge.
            out.extend(search_bazos(client, make=make, model=model, limit=per))
    # dedupe within live
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for offer in out:
        key = f"{offer.get('source')}:{offer.get('externalId')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(offer)
    return unique[:limit]
