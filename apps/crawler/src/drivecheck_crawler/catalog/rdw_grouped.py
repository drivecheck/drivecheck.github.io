from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime

import httpx

from drivecheck_crawler.catalog.normalize import (
    clean_model_name,
    display_make,
    infer_transmission,
    map_body,
    map_category,
    motorization_label,
)
from drivecheck_crawler.catalog.repository import VariantRow

log = logging.getLogger(__name__)

RDW_VEHICLES = "https://opendata.rdw.nl/resource/m9d7-ebf2.json"

SOORTEN = (
    "Personenauto",
    "Bedrijfsauto",
    "Motorfiets",
    "Bromfiets",
    "Aanhangwagen",
    "Middenasaanhangwagen",
)


def iter_rdw_grouped_variants(
    client: httpx.Client,
    *,
    max_groups: int = 200_000,
    page_size: int = 50_000,
) -> Iterator[VariantRow]:
    """Broad real register combos via SoQL GROUP BY (fuel/power may be Neuvedeno)."""
    produced = 0
    per_type = max(5_000, max_groups // len(SOORTEN))
    for soort in SOORTEN:
        offset = 0
        type_count = 0
        while produced < max_groups and type_count < per_type:
            select = (
                "merk,handelsbenaming,voertuigsoort,"
                "date_extract_y(datum_eerste_toelating_dt) as year,"
                "inrichting,cilinderinhoud,count(*)"
            )
            limit = min(page_size, per_type - type_count)
            params = {
                "$select": select,
                "$where": f"voertuigsoort='{soort}' AND merk IS NOT NULL AND handelsbenaming IS NOT NULL",
                "$group": "merk,handelsbenaming,voertuigsoort,year,inrichting,cilinderinhoud",
                "$order": "count desc",
                "$limit": str(limit),
                "$offset": str(offset),
            }
            resp = client.get(RDW_VEHICLES, params=params, timeout=120.0)
            resp.raise_for_status()
            rows = resp.json()
            if not rows:
                break
            for row in rows:
                category = map_category(row.get("voertuigsoort"), row.get("inrichting"))
                if not category:
                    continue
                try:
                    year = int(row.get("year"))
                except (TypeError, ValueError):
                    continue
                if year < 1950 or year > datetime.now().year + 1:
                    continue
                make_raw = (row.get("merk") or "").strip()
                model_raw = (row.get("handelsbenaming") or "").strip()
                if not make_raw or not model_raw:
                    continue
                make = display_make(make_raw)
                if not make:
                    continue
                model = clean_model_name(model_raw, make)
                try:
                    displacement_cc = int(float(row["cilinderinhoud"])) if row.get("cilinderinhoud") else None
                except ValueError:
                    displacement_cc = None
                if displacement_cc is not None and displacement_cc <= 0:
                    displacement_cc = None
                body = map_body(row.get("inrichting"), category)
                transmission = infer_transmission(model_raw)
                fuel = "Neuvedeno"
                power_kw = None
                moto = motorization_label(displacement_cc, power_kw, fuel, model_raw)
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
                    source="rdw_grouped",
                )
                produced += 1
                type_count += 1
                if produced >= max_groups or type_count >= per_type:
                    break
            offset += len(rows)
            log.info(
                "RDW grouped soort=%s offset=%s type_count=%s produced=%s",
                soort,
                offset,
                type_count,
                produced,
            )
            if len(rows) < limit:
                break
