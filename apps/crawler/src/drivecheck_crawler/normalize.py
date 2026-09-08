from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from drivecheck_crawler.features import normalize_feature_list
from drivecheck_crawler.models import ListingDTO, SellerType


def parse_year(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 1950 <= value <= 2100 else None
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        n = int(round(value))
        return n if 1950 <= n <= 2100 else None
    text = str(value)
    m = re.search(r"(19|20)\d{2}", text)
    return int(m.group(0)) if m else None


def parse_int(value: object) -> int | None:
    """Parse a whole number from int/float/digit strings.

    Floats are rounded (``1700.0`` → 1700). Digit-stripping is only used for
    strings — never via ``str(float)``, which would turn ``2270.98`` into
    ``227098`` and poison EUR→CZK conversion.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return int(round(value))
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def parse_money_amount(value: object) -> float | None:
    """Parse a monetary amount preserving fractional units.

    Unlike :func:`parse_int` on strings, keeps decimal separators so
    ``\"2 270,98\"`` / ``2270.98`` stay ``2270.98`` (not ``227098``).
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return float(value) if value > 0 else None
    if isinstance(value, float):
        if not math.isfinite(value) or value <= 0:
            return None
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    cleaned = re.sub(r"[^\d,.\-]", "", text)
    if not cleaned or cleaned in {".", ",", "-", "-.", "-,"}:
        return None
    if "," in cleaned and "." in cleaned:
        # EU: 1.270,98 / US: 1,270.98 — last separator is decimal.
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        cleaned = (
            cleaned.replace(",", ".")
            if len(parts[-1]) <= 2
            else cleaned.replace(",", "")
        )
    try:
        n = float(cleaned)
    except ValueError:
        return None
    if not math.isfinite(n) or n <= 0:
        return None
    return n


def parse_price_czk(value: object) -> int | None:
    price = parse_int(value)
    if price is None or price < 5_000 or price > 50_000_000:
        return None
    return price


def cb_name(value: object) -> str | None:
    if isinstance(value, dict):
        name = value.get("name")
        return str(name) if name else None
    if value is None:
        return None
    return str(value)


def map_seller_type(*, premise: object | None, text_hints: str = "") -> SellerType:
    if premise:
        return "dealer"
    lowered = text_hints.lower()
    if any(x in lowered for x in ("autosalon", "autobazar", "s.r.o", "a.s.", "dealer")):
        return "dealer"
    if text_hints:
        return "private"
    return "unknown"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: object) -> datetime | None:
    """Parse ISO-ish timestamps from marketplace APIs into aware UTC datetimes."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


_PHONE_RE = re.compile(
    r"(\+?\d{3}[\s-]?)?\d{3}[\s-]?\d{3}[\s-]?\d{3}|\b\d{9}\b"
)
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)


def strip_contact_text(text: str) -> str:
    """Remove phones/emails if we ever keep free text (prefer not storing descriptions)."""
    cleaned = _PHONE_RE.sub("[redacted]", text)
    cleaned = _EMAIL_RE.sub("[redacted]", cleaned)
    return cleaned


def extract_features_from_text(text: str) -> list[str]:
    """Best-effort feature hints from Bazos title/body without storing the body."""
    candidates = [
        "panorama",
        "panoramatick",
        "sportline",
        "tažné",
        "tazne",
        "kamera",
        "navigace",
        "matrix",
        "keyless",
        "carplay",
        "android auto",
        "vyhřívan",
        "vyhrivan",
        "ventilovan",
        "kůže",
        "kuze",
        "tepelné čerpadlo",
        "tepelne cerpadlo",
        "4x4",
        "quattro",
        "xdrive",
        "4motion",
        "m sport",
        "amg",
        "s-line",
        "rs",
        "tempomat",
        "mrtvý úhel",
        "mrtvy uhel",
        "blind spot",
        "masáž",
        "masaz",
        "jízda v pruhu",
        "jizda v pruhu",
        "lane assist",
        "lane keep",
        "nezávislé topení",
        "nezavisle topeni",
        "webasto",
        "tovární záruka",
        "tovarni zaruka",
        "záruka výrobce",
        "vzduchový podvozek",
        "vzduchovy podvozek",
        "elektrický kufr",
        "elektricky kufr",
        "el. kufr",
        "power tailgate",
    ]
    found: list[str] = []
    lowered = text.lower()
    for c in candidates:
        if c in lowered:
            found.append(c)
    return normalize_feature_list(found)
