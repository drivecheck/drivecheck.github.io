"""Pure TipCars HTML / JSON-LD extractors (no network, no PII persistence)."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from drivecheck_crawler.catalog.normalize import map_fuel
from drivecheck_crawler.normalize import parse_int, parse_year

TIPCARS_ID_RE = re.compile(r"-(\d{5,})\.html(?:[?#].*)?$", re.I)
TIPCARS_SKU_RE = re.compile(r"(?:^|-)(\d{5,})$")

BODY_FROM_PATH = {
    "suv": "SUV",
    "kombi": "Kombi",
    "hatchback": "Hatchback",
    "sedan": "Sedan",
    "limuzina": "Sedan",
    "coupe": "Coupe",
    "cabrio": "Cabrio",
    "mpv": "MPV",
    "pick-up": "Pick-up",
    "pickup": "Pick-up",
    "dodavka": "Dodávka",
}


def extract_external_id(url: str, *, sku: str | None = None) -> str | None:
    if sku:
        m = TIPCARS_SKU_RE.search(sku.strip())
        if m:
            return m.group(1)
    m = TIPCARS_ID_RE.search((url or "").strip())
    return m.group(1) if m else None


def parse_json_ld_blocks(html: str) -> list[Any]:
    blocks: list[Any] = []
    for raw in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S,
    ):
        try:
            blocks.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return blocks


def find_item_list(blocks: list[Any]) -> dict[str, Any] | None:
    for block in blocks:
        if isinstance(block, dict) and block.get("@type") == "ItemList":
            return block
    return None


def find_product(blocks: list[Any]) -> dict[str, Any] | None:
    for block in blocks:
        if isinstance(block, dict) and block.get("@type") == "Product":
            return block
    return None


def _item_list_elements(item_list: dict[str, Any]) -> list[Any]:
    """TipCars SSR sometimes emits ``itemListElement`` as a dict keyed by
    ``\"0\"``/``\"1\"``… instead of a JSON array — treat both as a sequence.
    """
    raw = item_list.get("itemListElement") or []
    if isinstance(raw, dict):
        # Prefer numeric key order when keys look like indices.
        try:
            return [raw[k] for k in sorted(raw.keys(), key=lambda x: int(str(x)))]
        except (TypeError, ValueError):
            return list(raw.values())
    if isinstance(raw, list):
        return raw
    return []


def list_products_from_html(html: str) -> list[dict[str, Any]]:
    item_list = find_item_list(parse_json_ld_blocks(html))
    if not item_list:
        return []
    out: list[dict[str, Any]] = []
    for el in _item_list_elements(item_list):
        if not isinstance(el, dict):
            continue
        item = el.get("item")
        if isinstance(item, dict) and item.get("@type") == "Product":
            # Some cards omit ``url`` but keep ``@id``.
            if not item.get("url") and isinstance(item.get("@id"), str):
                item = {**item, "url": item["@id"]}
            out.append(item)
    return out


def props_map(product: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for prop in product.get("additionalProperty") or []:
        if not isinstance(prop, dict):
            continue
        name = str(prop.get("name") or "").strip()
        value = str(prop.get("value") or "").strip()
        if name and value:
            out[name.casefold()] = value
    return out


def prop_get(props: dict[str, str], *names: str) -> str | None:
    for name in names:
        v = props.get(name.casefold())
        if v:
            return v
    return None


def parse_mileage_km(raw: str | None) -> int | None:
    if not raw:
        return None
    # Reject EV/range phrasing if it ever appears near dojezd.
    if re.search(r"dojezd|wltp|bater", raw, re.I):
        return None
    m = re.search(r"(\d[\d\s.\u00a0]{0,12})\s*km", raw, re.I)
    if not m:
        return None
    n = parse_int(m.group(1))
    if n is None or n < 0 or n > 2_000_000:
        return None
    return n


def parse_month_year(raw: str | None) -> int | None:
    if not raw:
        return None
    m = re.search(r"(?:^|\D)(\d{1,2})\s*/\s*((?:19|20)\d{2})", raw)
    if m:
        return parse_year(m.group(2))
    return parse_year(raw)


def map_transmission_tipcars(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.casefold()
    if "dsg" in s or "dvojspoj" in s:
        return "DSG"
    if "cvt" in s:
        return "CVT"
    if "aut" in s or "automat" in s:
        return "Automatická"
    if "man" in s:
        return "Manuální"
    return None


def map_drive_tipcars(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.casefold()
    if "4x4" in s or "4wd" in s or "awd" in s or "všech" in s or "vsech" in s:
        return "4×4"
    if "přední" in s or "predni" in s or "fwd" in s:
        return "Přední"
    if "zadní" in s or "zadni" in s or "rwd" in s:
        return "Zadní"
    return None


def body_from_url(url: str) -> str | None:
    path = urlparse(url).path.lower()
    for token, body in BODY_FROM_PATH.items():
        if f"/{token}/" in path:
            return body
    return None


def fuel_from_url(url: str) -> str | None:
    path = urlparse(url).path.lower()
    for token in ("nafta", "benzin", "benzín", "hybrid", "elektro", "lpg", "cng"):
        if f"/{token}/" in path or f"/{token.replace('í', 'i')}/" in path:
            return map_fuel(token)
    return None


def parse_max_list_page(html: str, *, page_size: int = 20) -> int | None:
    """Highest `str=N-{page_size}` page index found in list HTML."""
    best = 0
    for m in re.finditer(rf"str=(\d+)-{page_size}\b", html):
        best = max(best, int(m.group(1)))
    return best or None


def region_from_product(product: dict[str, Any]) -> str | None:
    """Broad locality only — never street / phone / email / seller name."""
    offers = product.get("offers")
    if not isinstance(offers, dict):
        return None
    seller = offers.get("seller")
    if not isinstance(seller, dict):
        return None
    address = seller.get("address")
    if not isinstance(address, dict):
        return None
    locality = address.get("addressLocality")
    if locality and str(locality).strip():
        return str(locality).strip()
    return None


def seller_is_organization(product: dict[str, Any]) -> bool:
    offers = product.get("offers")
    if not isinstance(offers, dict):
        return False
    seller = offers.get("seller")
    if not isinstance(seller, dict):
        return False
    return seller.get("@type") == "Organization"


def first_image_url(product: dict[str, Any]) -> str | None:
    """Cover URL from JSON-LD ``image`` (absolutize // and / paths)."""
    candidates: list[str] = []
    image = product.get("image")
    if isinstance(image, str):
        candidates.append(image)
    elif isinstance(image, list) and image:
        first = image[0]
        if isinstance(first, str):
            candidates.append(first)
        elif isinstance(first, dict):
            for key in ("url", "contentUrl", "@id"):
                raw = first.get(key)
                if isinstance(raw, str) and raw.strip():
                    candidates.append(raw)
                    break

    for raw in candidates:
        abs_url = absolute_tipcars_url(raw)
        if abs_url.startswith(("http://", "https://")):
            return abs_url
    return None


def offer_price_czk(product: dict[str, Any]) -> int | None:
    offers = product.get("offers")
    if not isinstance(offers, dict):
        return None
    currency = str(offers.get("priceCurrency") or "CZK").upper()
    if currency not in ("CZK", "KC", "KČ"):
        return None
    return parse_int(offers.get("price"))


# Common CZ makes for list-card titles (JSON-LD often omits brand on /osobni).
_KNOWN_MAKES = (
    "Alfa Romeo",
    "Mercedes-Benz",
    "Land Rover",
    "Aston Martin",
    "Volkswagen",
    "Škoda",
    "Skoda",
    "Citroën",
    "Citroen",
    "Hyundai",
    "Renault",
    "Peugeot",
    "Toyota",
    "Nissan",
    "Mazda",
    "Honda",
    "Suzuki",
    "Subaru",
    "Mitsubishi",
    "Porsche",
    "Jaguar",
    "Lexus",
    "Volvo",
    "Dacia",
    "Cupra",
    "Seat",
    "Audi",
    "BMW",
    "Ford",
    "Opel",
    "Fiat",
    "Kia",
    "Mini",
    "Tesla",
    "Jeep",
)


def brand_name(product: dict[str, Any]) -> str | None:
    brand = product.get("brand")
    if isinstance(brand, dict):
        name = brand.get("name")
        if name and str(name).strip():
            return str(name).strip()
    if isinstance(brand, str) and brand.strip():
        return brand.strip()
    return None


def make_model_from_title(title: str | None) -> tuple[str | None, str | None]:
    if not title:
        return None, None
    text = title.strip()
    for make in sorted(_KNOWN_MAKES, key=len, reverse=True):
        if text.casefold().startswith(make.casefold()):
            rest = text[len(make) :].strip(" -–|/")
            model = rest.split()[0].strip(",.;") if rest else None
            display_make = "Škoda" if make.casefold() in ("skoda", "škoda") else make
            if display_make == "Citroen":
                display_make = "Citroën"
            return display_make, model or None
    return None, None


def model_name(product: dict[str, Any], *, make: str | None = None) -> str | None:
    raw = product.get("model")
    if isinstance(raw, dict):
        name = raw.get("name")
        if name and str(name).strip():
            return str(name).strip()
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    # Fallback: strip make prefix from Product.name (list cards).
    title = str(product.get("name") or "").strip()
    if not title:
        return None
    if make and title.casefold().startswith(make.casefold()):
        rest = title[len(make) :].strip(" -–|/")
        if rest:
            return rest.split()[0].strip(",.;") or None
    _, model = make_model_from_title(title)
    return model


def parse_power_kw(raw: str | None) -> int | None:
    if not raw:
        return None
    m = re.search(r"(\d{2,3})\s*kW\b", raw, re.I)
    if m:
        n = int(m.group(1))
        return n if 20 <= n <= 1500 else None
    m = re.search(r"^(\d{2,3})$", raw.strip())
    if m:
        n = int(m.group(1))
        return n if 20 <= n <= 1500 else None
    return None


def parse_displacement_cc(raw: str | None) -> int | None:
    if not raw:
        return None
    m = re.search(r"(\d[\d\s.\u00a0]{0,8})\s*(?:ccm|cm\s*3|cm³)\b", raw, re.I)
    if m:
        n = parse_int(m.group(1))
        if n is not None and 600 <= n <= 10_000:
            return n
    m = re.search(r"^(\d{3,4})$", raw.strip())
    if m:
        n = int(m.group(1))
        return n if 600 <= n <= 10_000 else None
    return None


def absolute_tipcars_url(url: str) -> str:
    u = (url or "").strip()
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return "https://www.tipcars.com" + u
    return u


def fuel_from_props(props: dict[str, str]) -> str | None:
    raw = prop_get(
        props, "palivo", "druh paliva", "typ paliva", "fuel", "typ_paliva"
    )
    if not raw:
        return None
    mapped = map_fuel(raw)
    return None if mapped == "Neuvedeno" else mapped


def fields_from_product(product: dict[str, Any]) -> dict[str, Any] | None:
    """Map JSON-LD Product → commercial listing fields (no PII / VIN).

    Intentionally ignores: productID, seller name, telephone, email,
    streetAddress, postalCode. Detail pages often omit ``url`` but keep
    ``sku`` like ``…-11300095`` — callers merge list URL back in.
    """
    url = absolute_tipcars_url(str(product.get("url") or ""))
    sku = product.get("sku")
    sku_s = str(sku).strip() if sku is not None else None
    # Prefer numeric listing id from URL/sku; never use productID (VIN-like).
    external_id = extract_external_id(url, sku=sku_s)
    price = offer_price_czk(product)
    if not external_id or price is None:
        return None
    if url and not url.startswith("http"):
        return None
    if price < 5_000 or price > 50_000_000:
        return None

    props = props_map(product)
    title = str(product.get("name") or "").strip() or None
    make = brand_name(product)
    if not make:
        make, _ = make_model_from_title(title)
    model = model_name(product, make=make)

    mileage = parse_mileage_km(
        prop_get(props, "najeto", "nájezd", "najezd", "tachometr", "mileage")
    )
    year = parse_month_year(
        prop_get(
            props,
            "uvedení do provozu",
            "uvedeni do provozu",
            "rok výroby",
            "rok vyroby",
            "výroba",
            "vyroba",
        )
    )
    fuel = fuel_from_props(props) or (fuel_from_url(url) if url else None)
    transmission = map_transmission_tipcars(
        prop_get(props, "převodovka", "prevodovka", "transmission", "gearbox")
    )
    drive = map_drive_tipcars(prop_get(props, "pohon", "drive", "pohon kol"))
    power_kw = parse_power_kw(
        prop_get(props, "výkon", "vykon", "výkon motoru", "vykon motoru", "power", "kw")
    )
    displacement_cc = parse_displacement_cc(
        prop_get(
            props,
            "objem",
            "objem motoru",
            "zdvihový objem",
            "zdvihovy objem",
            "ccm",
            "cm3",
        )
    )
    body = body_from_url(url) if url else None

    seller_type = "dealer" if seller_is_organization(product) else "unknown"
    region = region_from_product(product)

    return {
        "external_id": external_id,
        "url": url or None,
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
        "price_czk": price,
        "image_url": first_image_url(product),
        "title": title,
    }


def merge_field_dicts(
    base: dict[str, Any], enrich: dict[str, Any]
) -> dict[str, Any]:
    """Prefer enrich non-None values over base (keep list URL when detail omits it)."""
    out = dict(base)
    for key, value in enrich.items():
        if value is None or value == "":
            continue
        out[key] = value
    return out
