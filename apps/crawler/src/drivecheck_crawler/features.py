from __future__ import annotations

import re
import unicodedata

# High-value / pricing-relevant equipment → stable keys.
# Unmapped names fall back to a slug so we still accumulate market stats.
FEATURE_ALIASES: dict[str, str] = {
    # Keys are accent-stripped lowercase (see normalize_feature_name).
    "kozene sedacky": "leather_seats",
    "kuze": "leather_seats",
    "vyhrivana sedadla": "heated_seats",
    "vyhrivana predni sedadla": "heated_seats",
    "vyhrivan": "heated_seats",
    "ventilovana sedadla": "ventilated_seats",
    "ventilovan": "ventilated_seats",
    "parkovaci kamera": "parking_camera",
    "kamera": "parking_camera",
    "360 kamera": "camera_360",
    "parkovaci senzory": "parking_sensors",
    "navigace": "navigation",
    "apple car play": "apple_carplay",
    "apple carplay": "apple_carplay",
    "android auto": "android_auto",
    "matrix": "matrix_lights",
    "matrix svetlomety": "matrix_lights",
    "led svetlomety": "led_lights",
    "xenonove svetlomety": "xenon_lights",
    "keyless": "keyless",
    "keyless entry": "keyless",
    "keyless go": "keyless",
    "bezklicove odemykani": "keyless",
    "bezklicovy pristup": "keyless",
    "sportline": "sportline",
    "rs": "rs_package",
    "m sport": "m_sport",
    "amg": "amg",
    "s-line": "s_line",
    "s line": "s_line",
    "4x4": "awd",
    "pohon vsech kol": "awd",
    "quattro": "awd",
    "xdrive": "awd",
    "4motion": "awd",
    "servisni knizka": "service_book",
    "tepelne cerpadlo": "heat_pump",
    "adaptivni tempomat": "cruise_control",
    "tempomat": "cruise_control",
    "panorama": "panorama",
    "panoramaticka strecha": "panorama",
    "tazne zarizeni": "tow_hitch",
    "tazne": "tow_hitch",
    "head-up display": "hud",
    "head up display": "hud",
    "hud": "hud",
    "abs": "abs",
    "esp": "esp",
    # Drivecheck equipment filter catalog (14 icons)
    "mrtvy uhel": "blind_spot",
    "hlidani mrtveho uhlu": "blind_spot",
    "blind spot": "blind_spot",
    "bsm": "blind_spot",
    "elektricke otevirani kufru": "electric_tailgate",
    "elektricky kufr": "electric_tailgate",
    "el kufr": "electric_tailgate",
    "power tailgate": "electric_tailgate",
    "vyklopne viko": "electric_tailgate",
    "masazni sedadla": "massage_seats",
    "masazni kresla": "massage_seats",
    "masaz": "massage_seats",
    "massage": "massage_seats",
    "jizda v pruhu": "lane_assist",
    "jizda v pruzich": "lane_assist",
    "lane assist": "lane_assist",
    "lane keep": "lane_assist",
    "lane keeping": "lane_assist",
    "udrzovani v pruhu": "lane_assist",
    "nezavisle topeni": "aux_heater",
    "webasto": "aux_heater",
    "parking heater": "aux_heater",
    "pridavne topeni": "aux_heater",
    "tovarni zaruka": "factory_warranty",
    "zaruka vyrobce": "factory_warranty",
    "manufacturer warranty": "factory_warranty",
    "vzduchovy podvozek": "air_suspension",
    "vzduchove odpruzeni": "air_suspension",
    "air suspension": "air_suspension",
    # German (Mobile.de / AutoScout24) — map into same CZ vocabulary keys
    "sitzheizung": "heated_seats",
    "geheizte sitze": "heated_seats",
    "sitzbeluftung": "ventilated_seats",
    "beluftete sitze": "ventilated_seats",
    "ledersitze": "leather_seats",
    "leder": "leather_seats",
    "navigationssystem": "navigation",
    "navigation": "navigation",
    "navi": "navigation",
    "panoramadach": "panorama",
    "panorama-dach": "panorama",
    "schiebedach": "panorama",
    "tempomat": "cruise_control",
    "abstandstempomat": "cruise_control",
    "adaptiver tempomat": "cruise_control",
    "einparkhilfe": "parking_sensors",
    "parkassistent": "parking_sensors",
    "ruckfahrkamera": "parking_camera",
    "parkkamera": "parking_camera",
    "kamera": "parking_camera",
    "spurhalteassistent": "lane_assist",
    "spurassistent": "lane_assist",
    "totwinkelassistent": "blind_spot",
    "blindspot": "blind_spot",
    "schlusseloses zugangssystem": "keyless",
    "keyless go": "keyless",
    "keyless entry": "keyless",
    "anhangerkupplung": "tow_hitch",
    "anhaengerkupplung": "tow_hitch",
    "standheizung": "aux_heater",
    "luftfederung": "air_suspension",
    "massagesitze": "massage_seats",
    "elektrische heckklappe": "electric_tailgate",
}


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def slugify_feature(name: str) -> str:
    text = _strip_accents(name).lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")[:64]


def normalize_feature_name(name: str) -> str | None:
    if not name or not name.strip():
        return None
    key = _strip_accents(name).lower().strip()
    key = re.sub(r"\s+", " ", key)
    if key in FEATURE_ALIASES:
        return FEATURE_ALIASES[key]
    # Prefer longer aliases first so "adaptivni tempomat" beats "tempomat".
    for alias, mapped in sorted(FEATURE_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if alias in key:
            return mapped
    return slugify_feature(name)


def normalize_feature_list(names: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = normalize_feature_name(name)
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def map_known_feature(name: str) -> str | None:
    """Map to vocabulary key or None — skip unknown junk (import portals)."""
    if not name or not name.strip():
        return None
    key = _strip_accents(name).lower().strip()
    key = re.sub(r"\s+", " ", key)
    if key in FEATURE_ALIASES:
        return FEATURE_ALIASES[key]
    for alias, mapped in sorted(FEATURE_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if alias in key:
            return mapped
    return None


def normalize_known_feature_list(names: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = map_known_feature(name)
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out
