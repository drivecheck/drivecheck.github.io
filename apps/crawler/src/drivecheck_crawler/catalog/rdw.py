from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import httpx

from drivecheck_crawler.catalog.normalize import (
    clean_model_name,
    display_make,
    infer_transmission,
    map_body,
    map_category,
    map_fuel,
    motorization_label,
)
from drivecheck_crawler.catalog.repository import VariantRow

log = logging.getLogger(__name__)

RDW_VEHICLES = "https://opendata.rdw.nl/resource/m9d7-ebf2.json"
RDW_FUEL = "https://opendata.rdw.nl/resource/8ys7-d773.json"

VOERTUIGSOORTEN = (
    "Personenauto",
    "Bedrijfsauto",
    "Motorfiets",
    "Bromfiets",
    "Aanhangwagen",
    "Middenasaanhangwagen",
)


def _parse_year(value: str | None) -> int | None:
    if not value:
        return None
    try:
        if "T" in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).year
        if len(value) >= 4 and value[:4].isdigit():
            return int(value[:4])
    except ValueError:
        return None
    return None


def _parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(float(str(value).replace(",", ".")))
        return number if number > 0 else None
    except ValueError:
        return None


def _fetch_fuels(client: httpx.Client, plates: list[str]) -> dict[str, dict[str, Any]]:
    if not plates:
        return {}
    # Socrata IN clause
    quoted = ",".join(f"'{p}'" for p in plates)
    url = f"{RDW_FUEL}?$where=kenteken in ({quoted})&$limit={len(plates) * 3}"
    resp = client.get(url, timeout=120.0)
    resp.raise_for_status()
    out: dict[str, dict[str, Any]] = {}
    for row in resp.json():
        plate = row.get("kenteken")
        if not plate or plate in out:
            continue
        out[plate] = row
    return out


def iter_rdw_variants(
    client: httpx.Client,
    *,
    max_rows: int = 250_000,
    page_size: int = 500,
) -> Iterator[VariantRow]:
    """Stratified plate stream → fuel join → variants."""
    per_type = max(1, max_rows // len(VOERTUIGSOORTEN))
    produced = 0
    seen: set[tuple] = set()

    for soort in VOERTUIGSOORTEN:
        offset = 0
        type_count = 0
        while type_count < per_type and produced < max_rows:
            params = {
                "$select": (
                    "kenteken,merk,handelsbenaming,voertuigsoort,inrichting,"
                    "cilinderinhoud,datum_eerste_toelating_dt"
                ),
                "$where": f"voertuigsoort='{soort}' AND merk IS NOT NULL",
                "$order": "kenteken",
                "$limit": str(min(page_size, per_type - type_count)),
                "$offset": str(offset),
            }
            resp = client.get(RDW_VEHICLES, params=params, timeout=120.0)
            resp.raise_for_status()
            rows = resp.json()
            if not rows:
                break

            fuels = _fetch_fuels(client, [r["kenteken"] for r in rows if r.get("kenteken")])
            for row in rows:
                category = map_category(row.get("voertuigsoort"), row.get("inrichting"))
                if not category:
                    continue
                year = _parse_year(row.get("datum_eerste_toelating_dt"))
                make_raw = (row.get("merk") or "").strip()
                model_raw = (row.get("handelsbenaming") or "").strip()
                if not year or not make_raw or not model_raw:
                    continue
                if year < 1950 or year > datetime.now().year + 1:
                    continue

                fuel_row = fuels.get(row.get("kenteken") or "", {})
                fuel = map_fuel(fuel_row.get("brandstof_omschrijving"))
                power_kw = _parse_int(fuel_row.get("nettomaximumvermogen"))
                displacement_cc = _parse_int(row.get("cilinderinhoud"))
                make = display_make(make_raw)
                if not make:
                    continue
                model = clean_model_name(model_raw, make)
                body = map_body(row.get("inrichting"), category)
                transmission = infer_transmission(model_raw)
                moto = motorization_label(displacement_cc, power_kw, fuel, model_raw)

                key = (
                    category,
                    make.lower(),
                    model.lower(),
                    year,
                    body,
                    fuel,
                    transmission,
                    moto,
                    power_kw,
                    displacement_cc,
                )
                if key in seen:
                    continue
                seen.add(key)

                yield VariantRow(
                    make=make,
                    model=model,
                    category=category,
                    year=year,
                    body=body,
                    fuel=fuel,
                    transmission=transmission,
                    motorization_label=moto,
                    power_kw=power_kw,
                    displacement_cc=displacement_cc,
                    engine_code=None,
                    source="rdw",
                )
                produced += 1
                type_count += 1
                if produced >= max_rows:
                    return

            offset += len(rows)
            log.info(
                "RDW progress soort=%s offset=%s produced=%s unique=%s",
                soort,
                offset,
                produced,
                len(seen),
            )
            if len(rows) < page_size:
                break
