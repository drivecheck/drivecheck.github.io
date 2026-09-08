from __future__ import annotations

import re
import unicodedata


FUEL_MAP = {
    "benzine": "Benzín",
    "benzín": "Benzín",
    "benzin": "Benzín",
    "gasoline": "Benzín",
    "petrol": "Benzín",
    "diesel": "Nafta",
    "nafta": "Nafta",
    "elektriciteit": "Elektro",
    "electriciteit": "Elektro",
    "electric": "Elektro",
    "elektro": "Elektro",
    "elektrisch": "Elektro",
    "lpg": "LPG",
    "cng": "CNG",
    "waterstof": "Vodík",
    "hydrogen": "Vodík",
    "vodík": "Vodík",
    "alcohol": "Ostatní",
    "lng": "Ostatní",
    "hybride": "Hybrid",
    "hybrid": "Hybrid",
}

BODY_MAP = {
    "hatchback": "Hatchback",
    "sedan": "Sedan",
    "stationwagen": "Kombi",
    "stationwagen / combi": "Kombi",
    "combi": "Kombi",
    "kombi": "Kombi",
    "coupe": "Coupe",
    "coupé": "Coupe",
    "cabriolet": "Cabrio",
    "cabrio": "Cabrio",
    "mpv": "MPV",
    "suv": "SUV",
    "terreinwagen": "SUV",
    "terreinvoertuig": "SUV",
    "limousine": "Sedan",
    "pick-up": "Pick-up",
    "pickup": "Pick-up",
    "bestel": "Dodávka",
    "gesloten opbouw": "Dodávka",
    "open laadbak": "Pick-up",
    "chassis cabine": "Dodávka",
    "woonwagen": "Karavan",
    "caravan": "Karavan",
    "kampeerwagen": "Karavan",
    "motorfiets": "Motocykl",
}

# Dutch specialty bodies that are not useful for CZ dealer appraisal UI.
BODY_BLOCKLIST = {
    "voor rolstoelen toegankelijk voertuig",
    "niet geregistreerd",
    "lijkwagen",
    "ambulance",
    "speciale groep",
    "niet nader aangeduid",
    "bergingsvoertuig",
    "voor vervoer voertuigen",
    "bus",
}

MAKE_DISPLAY = {
    "volkswagen": "Volkswagen",
    "vw": "Volkswagen",
    "mercedes-benz": "Mercedes-Benz",
    "mercedes": "Mercedes-Benz",
    "mercedes-amg": "Mercedes-Benz",
    "bmw": "BMW",
    "bmw i": "BMW",
    "skoda": "Škoda",
    "škoda": "Škoda",
    "citroen": "Citroën",
    "citroën": "Citroën",
    "opel": "Opel",
    "seat": "Seat",
    "cupra": "Cupra",
    "audi": "Audi",
    "quattro": "Audi",
    "ford": "Ford",
    "ford-cng-technik": "Ford",
    "toyota": "Toyota",
    "hyundai": "Hyundai",
    "kia": "Kia",
    "renault": "Renault",
    "peugeot": "Peugeot",
    "volvo": "Volvo",
    "mazda": "Mazda",
    "honda": "Honda",
    "nissan": "Nissan",
    "fiat": "Fiat",
    "dacia": "Dacia",
    "suzuki": "Suzuki",
    "mitsubishi": "Mitsubishi",
    "porsche": "Porsche",
    "mini": "Mini",
    "tesla": "Tesla",
    "land rover": "Land Rover",
    "alfa romeo": "Alfa Romeo",
    "daimlerchrysler ag": "Chrysler",
    "daimlerchrysler": "Chrysler",
    "daimlerchrysler (usa)": "Chrysler",
    "jaguar cars": "Jaguar",
    "jaguar land rover": "Land Rover",
    "mc laren": "McLaren",
    "rolls royce": "Rolls-Royce",
    "ds": "DS",
}

# Corporate / specialty register names we never want as distinct brands.
# (Aliases belong in MAKE_DISPLAY — do not blocklist names we remap.)
MAKE_BLOCKLIST = {
    "3a3",
    "concorde reisemobile gmbh",
    "b-style & flex-i-trans",
    "yueda-human horizons",
}


def normalize_key(value: str) -> str:
    text = unicodedata.normalize("NFD", value or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text).strip().lower()


def display_make(raw: str) -> str | None:
    key = normalize_key(raw)
    if key in MAKE_BLOCKLIST:
        return None
    if key in MAKE_DISPLAY:
        return MAKE_DISPLAY[key]
    # Reject corporate suffixes / specialty tags
    if any(x in key for x in (" gmbh", " ag", " technik", "cng-technik", "(usa)", "(su)")):
        if key not in MAKE_DISPLAY:
            return None
    return " ".join(part.capitalize() for part in raw.strip().split())


def map_fuel(raw: str | None) -> str:
    if not raw:
        return "Neuvedeno"
    key = normalize_key(raw)
    if key in FUEL_MAP:
        return FUEL_MAP[key]
    for needle, label in FUEL_MAP.items():
        if needle in key:
            return label
    return raw.strip().title()


def map_body(raw: str | None, category: str) -> str:
    if not raw:
        if category == "motorcycle":
            return "Motocykl"
        if category == "caravan":
            return "Karavan"
        if category == "van":
            return "Dodávka"
        return "Neuvedeno"
    key = normalize_key(raw)
    if key in BODY_BLOCKLIST:
        return "Neuvedeno"
    if key in BODY_MAP:
        return BODY_MAP[key]
    for needle, label in BODY_MAP.items():
        if needle in key:
            return label
    return "Neuvedeno"


def infer_transmission(handelsbenaming: str | None) -> str:
    text = normalize_key(handelsbenaming or "")
    if any(x in text for x in ("dsg", "cvt", "automaat", "automatic", "tiptronic", "pdk", "e-cvt")):
        if "cvt" in text or "e-cvt" in text:
            return "CVT"
        if "dsg" in text:
            return "DSG / dvojspojka"
        return "Automatická"
    if any(x in text for x in ("handgeschakeld", "manual", "manueel")):
        return "Manuální"
    return "Neuvedeno"


def map_category(voertuigsoort: str | None, inrichting: str | None = None) -> str | None:
    soort = normalize_key(voertuigsoort or "")
    body = normalize_key(inrichting or "")
    if "motorfiets" in soort or "bromfiets" in soort or "driewielig" in soort:
        return "motorcycle"
    if any(x in body for x in ("woon", "caravan", "kampeer")):
        return "caravan"
    if "aanhangwagen" in soort or "middenasaanhangwagen" in soort:
        if any(x in body for x in ("woon", "caravan", "kampeer")):
            return "caravan"
        return None
    if soort in {"bedrijfsauto", "bus"}:
        return "van"
    if soort == "personenauto":
        return "passenger"
    return None


def clean_model_name(handelsbenaming: str, make: str) -> str:
    model = (handelsbenaming or "").strip()
    make_u = make.strip().upper()
    if model.upper().startswith(make_u + " "):
        model = model[len(make_u) :].strip()
    model = re.sub(r"\s+", " ", model)
    # Strip trailing power / engine marketing tails
    model = re.sub(r"\s+\d{2,4}\s*k[wW]\b.*$", "", model).strip()
    model = re.sub(
        r"\s+\d+[.,]\d+\s*(tdi|tsi|tfsi|tdci|scti|dci|hdi|cdi|gti|gtd|i|t|d)?\b.*$",
        "",
        model,
        flags=re.IGNORECASE,
    ).strip()
    model = re.sub(r"\s+\d+[.,]\d+\s*v\d\b.*$", "", model, flags=re.IGNORECASE).strip()
    model = re.sub(r"\s+v[68]\b.*$", "", model, flags=re.IGNORECASE).strip()
    # Drop pure numeric type codes
    if re.fullmatch(r"\d{3,}", model.replace(" ", "")):
        return model
    # Keep first 1–3 tokens for long commercial names
    tokens = model.split()
    if len(tokens) > 3:
        model = " ".join(tokens[:3])
    return model.title() if model.isupper() else model


def motorization_label(
    displacement_cc: int | None,
    power_kw: int | None,
    fuel: str,
    handelsbenaming: str | None = None,
) -> str:
    parts: list[str] = []
    if displacement_cc and displacement_cc > 0 and fuel != "Elektro":
        parts.append(f"{displacement_cc} ccm")
    if power_kw and power_kw > 0:
        parts.append(f"{power_kw} kW")
    if not parts and handelsbenaming:
        # fall back to trailing tokens from commercial name
        tokens = handelsbenaming.strip().split()
        tail = " ".join(tokens[-3:]) if len(tokens) > 1 else handelsbenaming.strip()
        return tail.title() if tail.isupper() else tail
    if not parts:
        return fuel if fuel != "Neuvedeno" else "Základní"
    return " ".join(parts)
