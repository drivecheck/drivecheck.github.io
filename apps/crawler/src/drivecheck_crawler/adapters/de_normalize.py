"""DE → CZ field maps for Mobile.de / AutoScout24.

Reuses catalog.normalize maps where possible; never store raw German labels
that would break Czech comps (fuel/transmission/drive/body).
"""

from __future__ import annotations

from drivecheck_crawler.catalog.normalize import (
    BODY_MAP,
    FUEL_MAP,
    display_make,
    map_body,
    map_fuel,
    normalize_key,
)

# Extra DE fuel tokens → catalog keys (then map_fuel → CZ labels).
_DE_FUEL_EXTRA = {
    "benzin": "Benzín",
    "super": "Benzín",
    "super plus": "Benzín",
    "super e10": "Benzín",
    "diesel": "Nafta",
    "elektro": "Elektro",
    "electric": "Elektro",
    "hybrid": "Hybrid",
    "plugin hybrid": "Hybrid",
    "plug-in-hybrid": "Hybrid",
    "plug in hybrid": "Hybrid",
    "erdgas": "CNG",
    "autogas": "LPG",
    "lpg": "LPG",
    "cng": "CNG",
    "wasserstoff": "Vodík",
    "andere": "Ostatní",
}

_DE_TRANSMISSION = {
    "schaltgetriebe": "Manuální",
    "manual": "Manuální",
    "manuell": "Manuální",
    "automatik": "Automatická",
    "automatic": "Automatická",
    "automatisiertes schaltgetriebe": "Automatická",
    "halbautomatik": "Automatická",
    "doppelkupplung": "DSG / dvojspojka",
    "dsg": "DSG / dvojspojka",
    "pdk": "DSG / dvojspojka",
    "cvt": "CVT",
}

_DE_DRIVE = {
    "frontantrieb": "Přední",
    "front": "Přední",
    " heckantrieb": "Zadní",  # leading space avoided below
    "heckantrieb": "Zadní",
    "rear": "Zadní",
    "allrad": "4x4",
    "allradantrieb": "4x4",
    "4x4": "4x4",
    "4wd": "4x4",
    "awd": "4x4",
    "quattro": "4x4",
    "xdrive": "4x4",
    "4motion": "4x4",
}

_DE_BODY_EXTRA = {
    "limousine": "Sedan",
    "kleinwagen": "Hatchback",
    "kombi": "Kombi",
    "estate": "Kombi",
    "gelaendewagen": "SUV",
    "geländewagen": "SUV",
    "suv": "SUV",
    "van": "MPV",
    "minivan": "MPV",
    "hochdachkombi": "MPV",
    "cabrio": "Cabrio",
    "cabriolet": "Cabrio",
    "coupe": "Coupe",
    "coupé": "Coupe",
    "transporter": "Dodávka",
    "lieferwagen": "Dodávka",
    "pickup": "Pick-up",
    "pick-up": "Pick-up",
}


def map_de_make(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    return display_make(str(raw).strip())


def map_de_fuel(raw: str | None) -> str | None:
    if not raw:
        return None
    key = normalize_key(raw)
    if key in _DE_FUEL_EXTRA:
        return _DE_FUEL_EXTRA[key]
    if key in FUEL_MAP:
        return map_fuel(raw)
    mapped = map_fuel(raw)
    return mapped if mapped != "Neuvedeno" else None


def map_de_transmission(raw: str | None) -> str | None:
    if not raw:
        return None
    key = normalize_key(raw)
    if key in _DE_TRANSMISSION:
        return _DE_TRANSMISSION[key]
    for needle, label in sorted(_DE_TRANSMISSION.items(), key=lambda kv: -len(kv[0])):
        if needle in key:
            return label
    return None


def map_de_drive(raw: str | None) -> str | None:
    if not raw:
        return None
    key = normalize_key(raw)
    if key in _DE_DRIVE:
        return _DE_DRIVE[key]
    for needle, label in sorted(_DE_DRIVE.items(), key=lambda kv: -len(kv[0])):
        if needle in key:
            return label
    return None


def map_de_body(raw: str | None) -> str | None:
    if not raw:
        return None
    key = normalize_key(raw)
    if key in _DE_BODY_EXTRA:
        return _DE_BODY_EXTRA[key]
    if key in BODY_MAP:
        mapped = map_body(raw, "passenger")
        return mapped if mapped != "Neuvedeno" else None
    mapped = map_body(raw, "passenger")
    return mapped if mapped != "Neuvedeno" else None
