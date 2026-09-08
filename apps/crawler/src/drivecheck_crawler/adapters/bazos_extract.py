"""Constrained fulltext field extraction for Bazos listings.

Bazos has no structured vehicle API — fields come from title + description
(and a few label rows). Prefer precision over recall: leave NULL when
ambiguous. Never extract contact/PII.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from drivecheck_crawler.normalize import parse_int, parse_year

# Manufacturing year window (used cars / recent stock).
_YEAR_MIN = 1990

# Odometer sanity for passenger cars.
_MILEAGE_MIN = 1_000
_MILEAGE_MAX = 1_500_000

# Power sanity (kW).
_POWER_KW_MIN = 20
_POWER_KW_MAX = 800

# Metric horsepower → kW (DIN PS).
_PS_TO_KW = 0.73549875

# Immediate prepositions that mark service/repair milestones, not odometer.
# Matches text immediately before a km figure, e.g. "po 8050 km", "v 120000 km".
_MILEAGE_BAD_PREFIX = re.compile(
    r"(?:"
    r"\bpo\s+(?:najet[ií]\s+)?"
    r"|\bv\s+"
    r"|\bp[řr]i\s+"
    r"|\brozvody?\s+(?:v|po)\s*"
    r")$",
    re.I,
)

# EV / tank range immediately before a km figure — not odometer.
# Anchored to end of left-context so an earlier "dojezd …" does not poison "najeto …".
_MILEAGE_RANGE_BEFORE = re.compile(
    r"(?:"
    r"\b(?:elektrick\w+\s+)?dojezd(?:\s+a[žz])?"
    r"(?:\s+na(?:\s+(?:n[áa]drž|baterii?))?)?"
    r"(?:\s+cca)?"
    r"|\bwltp"
    r"|\bnedc"
    r"|\brange"
    r"|\bbaterie"
    r")\s*$",
    re.I,
)
_MILEAGE_RANGE_AFTER = re.compile(
    r"^\s*(?:\(?\s*)?(?:wltp|nedc|epa)\b",
    re.I,
)
# Explicit odometer labels — never treat as range even if "dojezd" appears earlier.
_MILEAGE_ODOMETER_LABEL = re.compile(
    r"^(?:n[áa]jezd|najeto|tachometr|stav\s+(?:tachometru|km))\b",
    re.I,
)

# Number + optional thousands marker ("145 tis", "98 tis.").
_MILEAGE_NUM = r"(\d[\d\s.\u00a0]{0,11})\s*(tis\.?|tisíc)?"

# Explicit odometer labels (high confidence). Trailing km/tkm optional —
# Bazos often writes "Najeto 184000" / "Najeto: 184.000." without "km".
_MILEAGE_LABELED = re.compile(
    r"(?:"
    r"\bn[áa]jezd\b\s*:?\s*"
    r"|\bnajeto\b\s*:?\s*"
    r"|\btachometr\b\s*:?\s*"
    r"|\bstav\s+(?:tachometru|km)\s*:?\s*"
    r"|\bkm\s*:?\s*"
    r")"
    rf"{_MILEAGE_NUM}"
    r"(?:\s*t?km\b)?",
    re.I,
)

# Generic "… km" / "… tis. km" / "… tkm" candidates (must start with a digit).
_MILEAGE_GENERIC = re.compile(
    rf"(?<![/\d]){_MILEAGE_NUM}\s*(t?km)\b",
    re.I,
)

# Year labels (manufacturing / registration).
_YEAR_LABELED = (
    re.compile(r"rok\s*v[yý]roby\s*:?\s*([12]\d{3})\b", re.I),
    re.compile(r"\bro[čc]n[ií]k\s*:?\s*([12]\d{3})\b", re.I),
    re.compile(r"\brok\s*:?\s*([12]\d{3})\b", re.I),
    re.compile(r"\br\.?\s*v\.?\s*:?\s*([12]\d{3})\b", re.I),
    re.compile(r"\brv\s*:?\s*([12]\d{3})\b", re.I),
    re.compile(r"\bv[yý]roba\s*:?\s*([12]\d{3})\b", re.I),
    re.compile(r"\bv[yý]robeno\s*:?\s*([12]\d{3})\b", re.I),
    re.compile(
        r"\b(?:1\.?\s*)?regist\w*\s*:?\s*([12]\d{3})\b",
        re.I,
    ),
)

# Month/year manufacturing style: 09/2016, 9.2016 (also after r.v.)
_YEAR_MONTH = re.compile(r"\b(0?[1-9]|1[0-2])[./]([12]\d{3})\b")

# Bare year tokens (fallback only).
_YEAR_BARE = re.compile(r"\b(19[9]\d|20[0-3]\d)\b")

# Reject years when STK/inspection/phone/expiry labels sit immediately before.
_YEAR_BAD_BEFORE = re.compile(
    r"(?:"
    r"\bstk\b"
    r"|\btk\b"
    r"|\btechnick\w*"
    r"|\bplatn\w*"
    r"|\bzn[áa]mk\w*"
    r"|\bpojistk\w*"
    r"|\bgaranc\w*"
    r"|\btel\b"
    r"|\btelefon\w*"
    r"|\bdo\b"
    r")\s*[:.]?\s*$",
    re.I,
)
# Broader left-context noise for bare-year fallback.
_YEAR_BAD_NEAR = re.compile(
    r"\b(?:stk|tk|zn[áa]mk\w*|pojistk\w*|garanc\w*|tel|telefon|d[áa]lni[čc]n\w*)\b",
    re.I,
)

_FUEL_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bplug[-\s]?in\b|\bphev\b", re.I), "Hybrid"),
    (re.compile(r"\bhybrid\b|\bmhev\b", re.I), "Hybrid"),
    (re.compile(r"\belektro\b|\belectric\b|\bbev\b", re.I), "Elektro"),
    (re.compile(r"\blpg\b", re.I), "LPG"),
    (re.compile(r"\bcng\b", re.I), "CNG"),
    (
        re.compile(
            r"\bnafta\b|\bdiesel\b|\btdi\b|\bhdi\b|\bdci\b|\bbluehdi\b|\bcdti\b",
            re.I,
        ),
        "Nafta",
    ),
    (
        re.compile(r"\bbenzín\b|\bbenzin\b|\btsi\b|\btfsi\b|\bgdi\b|\bmpi\b|\bfsi\b", re.I),
        "Benzín",
    ),
)

_TRANSMISSION_AUTO = re.compile(
    r"\bautomatick|\bautomat\b|\bdsg\b|\bpdk\b|\bcvt\b|\btiptronic\b|\be[- ]?tronik\b",
    re.I,
)
_TRANSMISSION_MANUAL = re.compile(
    r"\bmanuál|\bmanual|\bmanuální|\bmanualni|\bp[řr]evodovka\s+manu",
    re.I,
)

_POWER_KW = re.compile(r"(?<![\d.])(\d{2,3})\s*kW\b", re.I)
_POWER_PS = re.compile(
    r"(?<![\d.])(\d{2,3})\s*(?:kon[ií]|kone|PS|hp)\b",
    re.I,
)

# Explicit displacement with unit.
_DISPLACEMENT_CC = re.compile(
    r"\b(\d{3,4})\s*(?:ccm|cm\s*3|cm³|cm3)\b",
    re.I,
)
# Liters with engine designation (safer than bare "1.4").
_DISPLACEMENT_LITERS = re.compile(
    r"\b([1-6][.,]\d)\s*"
    r"(?:tsi|tfsi|tdi|hdi|dci|gdi|mpi|fsi|cdti|bluehdi|multijet|ecoboost|skyactiv)?\b",
    re.I,
)

_BODY_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:combi|kombi)\b", re.I), "Kombi"),
    (re.compile(r"\bsedan\b|\blimuz[ií]na\b", re.I), "Sedan"),
    (re.compile(r"\bhatchback\b|\bliftback\b", re.I), "Hatchback"),
    (re.compile(r"\bsuv\b|\bcrossover\b", re.I), "SUV"),
    (re.compile(r"\b(?:coup[eé]|kupe)\b", re.I), "Coupe"),
    (re.compile(r"\b(?:cabrio|kabriolet|cabriolet)\b", re.I), "Cabrio"),
    (re.compile(r"\bmpv\b|\bvan\b|\bmonovolum", re.I), "MPV"),
    (re.compile(r"\bpick[-\s]?up\b", re.I), "Pick-up"),
)

_DRIVE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b4x4\b", re.I), "4x4"),
    (re.compile(r"\bquattro\b", re.I), "4x4"),
    (re.compile(r"\bxdrive\b", re.I), "4x4"),
    (re.compile(r"\b4motion\b", re.I), "4x4"),
    (re.compile(r"\b4wd\b|\bawd\b", re.I), "4x4"),
    (re.compile(r"\bpohon\s+v[šs]ech\s+kol\b", re.I), "4x4"),
)

# Locality that looks like street + phone / heavy digit contact noise.
_REGION_CONTACTISH = re.compile(
    r"(?:"
    r"\b(?:tel|telefon|mobil|email|e-mail|@)\b"
    r"|\d{6,}"
    r"|\+?\d[\d\s/-]{8,}\d"
    r"|\bul\.?\s"
    r"|\bulice\b"
    r")",
    re.I,
)


@dataclass(frozen=True, slots=True)
class BazosFields:
    year: int | None = None
    mileage_km: int | None = None
    fuel: str | None = None
    transmission: str | None = None
    power_kw: int | None = None
    displacement_cc: int | None = None
    body: str | None = None
    drive: str | None = None


def extract_fields(text: str) -> BazosFields:
    """Extract commercial vehicle fields from title + description text."""
    if not text or not text.strip():
        return BazosFields()
    return BazosFields(
        year=extract_year(text),
        mileage_km=extract_mileage_km(text),
        fuel=extract_fuel(text),
        transmission=extract_transmission(text),
        power_kw=extract_power_kw(text),
        displacement_cc=extract_displacement_cc(text),
        body=extract_body(text),
        drive=extract_drive(text),
    )


def _current_year() -> int:
    return datetime.now().year


def _year_ok(year: int | None) -> bool:
    if year is None:
        return False
    return _YEAR_MIN <= year <= _current_year() + 1


def extract_year(text: str) -> int | None:
    """Prefer labeled manufacturing year; reject STK/phone-adjacent years."""
    for pattern in _YEAR_LABELED:
        m = pattern.search(text)
        if not m:
            continue
        year = parse_year(m.group(1))
        if _year_ok(year):
            return year

    for m in _YEAR_MONTH.finditer(text):
        year = parse_year(m.group(2))
        left = re.sub(r"\s+", " ", text[max(0, m.start() - 24) : m.start()])
        if _year_ok(year) and not _YEAR_BAD_BEFORE.search(left):
            return year

    # Bare year fallback: only manufacturing-like years outside expiry/contact noise.
    candidates: list[int] = []
    for m in _YEAR_BARE.finditer(text):
        year = int(m.group(1))
        if not _year_ok(year):
            continue
        left = re.sub(r"\s+", " ", text[max(0, m.start() - 28) : m.start()])
        # Skip MM/YYYY tails already considered above, and STK/phone-adjacent years.
        if re.search(r"\d{1,2}[./]\s*$", left):
            continue
        if _YEAR_BAD_BEFORE.search(left) or _YEAR_BAD_NEAR.search(left):
            continue
        candidates.append(year)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) >= 2:
        # Manufacturing year + future expiry (známka/STK) often both appear as bare
        # years; keep the oldest plausible car year when others look like expiry.
        now = _current_year()
        car_years = [y for y in candidates if y <= now]
        futureish = [y for y in candidates if y > now]
        if len(car_years) == 1 and futureish:
            return car_years[0]
    return None


def _normalize_mileage(raw: str, *, tis: bool = False, tkm: bool = False) -> int | None:
    mileage = parse_int(raw.replace("\u00a0", " "))
    if mileage is None:
        return None
    if (tis or tkm) and mileage < 2_000:
        mileage *= 1000
    if _MILEAGE_MIN <= mileage <= _MILEAGE_MAX:
        return mileage
    return None


def _mileage_rejected(text: str, match: re.Match[str]) -> bool:
    """True when the km figure is repair milestone or EV/tank range, not odometer."""
    left = re.sub(r"\s+", " ", text[max(0, match.start() - 64) : match.start()])
    right = text[match.end() : match.end() + 16]
    matched = match.group(0)
    # "po 8050 km", "v 120000 km", "při 80 tis. km", "rozvody po …"
    if _MILEAGE_BAD_PREFIX.search(left):
        return True
    # Explicit najeto/tachometr labels win over an earlier "dojezd" mention.
    if not _MILEAGE_ODOMETER_LABEL.search(matched):
        # "dojezd 1310 km", "420 km WLTP", "dojezd na nádrž cca 900 km"
        if _MILEAGE_RANGE_BEFORE.search(left) or _MILEAGE_RANGE_AFTER.search(right):
            return True
    # "oprava motoru 8050 km" / "vyměněny rozvody 120000 km"
    if re.search(r"\b(?:oprav\w*|vym[ěe]n\w*|rozvod\w*)\b", left, re.I):
        return True
    return False


def extract_mileage_km(text: str) -> int | None:
    """Extract odometer reading; reject range / repair-context km figures."""
    labeled: list[int] = []
    for m in _MILEAGE_LABELED.finditer(text):
        if _mileage_rejected(text, m):
            continue
        # Label "km: N" / "najeto N" — group2 is optional tis/tisíc.
        tis = bool(m.group(2))
        # Full match text for tkm (group may be absent when unit is outside groups).
        unit_tkm = bool(re.search(r"tkm\b", m.group(0), re.I))
        value = _normalize_mileage(m.group(1), tis=tis, tkm=unit_tkm)
        if value is not None:
            labeled.append(value)
    if labeled:
        # Prefer the largest labeled reading (typical used-car odometer).
        return max(labeled)

    generics: list[int] = []
    for m in _MILEAGE_GENERIC.finditer(text):
        if _mileage_rejected(text, m):
            continue
        tis = bool(m.group(2))
        unit = (m.group(3) or "").lower()
        value = _normalize_mileage(m.group(1), tis=tis, tkm=unit == "tkm")
        if value is None:
            continue
        generics.append(value)

    if not generics:
        return None
    if len(generics) == 1:
        return generics[0]
    # Multiple unlabeled candidates → prefer largest (odometer vs short range).
    return max(generics)


def extract_fuel(text: str) -> str | None:
    for pattern, label in _FUEL_RULES:
        if pattern.search(text):
            return label
    return None


def extract_transmission(text: str) -> str | None:
    if _TRANSMISSION_AUTO.search(text):
        return "Automatická"
    if _TRANSMISSION_MANUAL.search(text):
        return "Manuální"
    return None


def extract_power_kw(text: str) -> int | None:
    m = _POWER_KW.search(text)
    if m:
        kw = int(m.group(1))
        if _POWER_KW_MIN <= kw <= _POWER_KW_MAX:
            return kw
    m = _POWER_PS.search(text)
    if m:
        ps = int(m.group(1))
        kw = int(round(ps * _PS_TO_KW))
        if _POWER_KW_MIN <= kw <= _POWER_KW_MAX:
            return kw
    return None


def extract_displacement_cc(text: str) -> int | None:
    m = _DISPLACEMENT_CC.search(text)
    if m:
        cc = int(m.group(1))
        if 600 <= cc <= 8000:
            return cc

    # Only accept liter form when an engine family token is present, or when
    # the match is clearly "X.Y TDI/TSI" style (group may be empty for bare —
    # require engine token for safety).
    for m in _DISPLACEMENT_LITERS.finditer(text):
        token = m.group(0)
        # Bare "1.4" without engine code is too weak — skip unless followed
        # by a known engine family (already in the regex optional group).
        if not re.search(
            r"(?:tsi|tfsi|tdi|hdi|dci|gdi|mpi|fsi|cdti|bluehdi|multijet|ecoboost|skyactiv)",
            token,
            re.I,
        ):
            continue
        liters = float(m.group(1).replace(",", "."))
        cc = int(round(liters * 1000))
        if 600 <= cc <= 8000:
            return cc
    return None


def extract_body(text: str) -> str | None:
    for pattern, label in _BODY_RULES:
        if pattern.search(text):
            return label
    return None


def extract_drive(text: str) -> str | None:
    for pattern, label in _DRIVE_RULES:
        if pattern.search(text):
            return label
    return None


def clean_region(raw: str | None) -> str | None:
    """Locality name only — drop ZIP prefixes and contact/address noise."""
    if not raw:
        return None
    loc = raw.strip()
    if not loc:
        return None
    if _REGION_CONTACTISH.search(loc):
        # Still allow "719 00 Ostrava" (ZIP + city) by stripping ZIP first.
        stripped = re.sub(r"^\d{3}\s*\d{2}\s*", "", loc).strip()
        if not stripped or _REGION_CONTACTISH.search(stripped):
            return None
        loc = stripped
    else:
        loc = re.sub(r"^\d{3}\s*\d{2}\s*", "", loc).strip()
    loc = loc.split("(")[0].strip()
    # Reject leftover digit-heavy strings (phones/streets with numbers).
    if not loc or re.search(r"\d{5,}", loc):
        return None
    if re.search(r"\b(?:tel|telefon|mobil|@)\b", loc, re.I):
        return None
    return loc or None
