"""Detect crashed / heavily damaged vehicles (CZ + DE marketplaces).

Product rule: accident / heavily damaged cars must not enter comps or browse.
Prefer skip-at-ingest; defense-in-depth filters also run on the web read path.

False positives to avoid: ordinary service language (serviska, nové brzdy, …).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

# Stable feature key when a row is tagged rather than dropped (legacy / soft path).
ACCIDENT_FEATURE_KEY = "accident_damaged"

# Strong CZ / DE crash signals (accent-stripped, lowercase).
# Intentionally require clear damage/accident wording — not generic "servis".
_ACCIDENT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        # Czech
        r"\bhavarovan",
        r"\bhavarie\b",
        r"\bhavarii\b",
        r"\bpo\s+nehode\b",
        r"\bpo\s+nehod[eě]\b",
        r"\bposkozen",
        r"\bpo\s+totalce\b",
        r"\bpo\s+totalni",
        r"\btotalk[ae]\b",
        r"\bna\s+nahradni\s+dily\b",
        r"\bna\s+nahradni\b",
        r"\bdemontovan",
        r"\bbouran",
        r"\bvrak\b",
        # German / import portals
        r"\bunfallwagen\b",
        r"\bunfallfahrzeug\b",
        r"\bunfall\b",
        r"\bunfallschaden\b",
        r"\bbeschadig",
        r"\bbastlerfahrzeug\b",
        r"\bbastler\b",
        r"\bfrontschaden\b",
        r"\bheckschaden\b",
        r"\bgetriebeschaden\b",
        r"\bmotorschaden\b",
        r"\btotalschaden\b",
        r"\bwirtschaftlicher\s+totalschaden\b",
        r"\baccident[- ]?damaged\b",
        r"\bsalvage\b",
        r"\brepairable\s+write[- ]?off\b",
    )
)

# Explicit boolean / enum flags from portal JSON (case-insensitive keys).
_TRUE_FLAG_KEYS = frozenset(
    {
        "iscurrentlydamaged",
        "currentlydamaged",
        "accidentdamaged",
        "hasaccident",
        "hasaccidents",
        "accident",
        "damaged",
        "isdamaged",
        "unfallwagen",
        "unfall",
        "bastlerfahrzeug",
    }
)

_TRUE_STRINGS = frozenset(
    {
        "1",
        "true",
        "yes",
        "ja",
        "y",
        "accident",
        "damaged",
        "unfall",
        "unfallwagen",
        "accidentdamaged",
        "bastlerfahrzeug",
    }
)

# specialConditions / tags that mean crash inventory on AS24 / Mobile.de.
_DAMAGE_TAG_NEEDLES = frozenset(
    {
        "accidentdamaged",
        "accident",
        "damaged",
        "unfall",
        "unfallwagen",
        "bastlerfahrzeug",
        "totalschaden",
        "iscurrentlydamaged",
    }
)


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_accident_text(value: str | None) -> str:
    if not value:
        return ""
    text = _strip_accents(str(value)).lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _truthy_flag(value: object) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, (int, float)) and value == 1:
        return True
    if isinstance(value, str):
        return normalize_accident_text(value).replace(" ", "") in _TRUE_STRINGS
    return False


def _iter_tag_texts(tags: object) -> Iterable[str]:
    if tags is None:
        return
    if isinstance(tags, str):
        yield tags
        return
    if isinstance(tags, Mapping):
        for k, v in tags.items():
            yield str(k)
            if v is not None and not isinstance(v, (dict, list)):
                yield str(v)
        return
    if isinstance(tags, Sequence) and not isinstance(tags, (str, bytes, bytearray)):
        for item in tags:
            if isinstance(item, str):
                yield item
            elif isinstance(item, Mapping):
                for k in ("name", "label", "id", "key", "value", "code"):
                    if item.get(k) is not None:
                        yield str(item[k])
            elif item is not None:
                yield str(item)


def text_suggests_accident_or_damage(text: str | None) -> bool:
    norm = normalize_accident_text(text)
    if not norm:
        return False
    return any(p.search(norm) for p in _ACCIDENT_PATTERNS)


def feature_keys_suggest_accident(feature_keys: Sequence[str] | None) -> bool:
    if not feature_keys:
        return False
    for key in feature_keys:
        k = normalize_accident_text(key).replace(" ", "_")
        if k == ACCIDENT_FEATURE_KEY or k in _DAMAGE_TAG_NEEDLES:
            return True
        if text_suggests_accident_or_damage(key):
            return True
    return False


def flags_suggest_accident(
    flags: Mapping[str, Any] | None = None,
    *,
    special_conditions: object = None,
) -> bool:
    if flags:
        for key, value in flags.items():
            nk = normalize_accident_text(str(key)).replace(" ", "").replace("_", "")
            if nk in _TRUE_FLAG_KEYS and _truthy_flag(value):
                return True
            if _truthy_flag(value) and text_suggests_accident_or_damage(str(key)):
                return True
    for tag in _iter_tag_texts(special_conditions):
        nt = normalize_accident_text(tag).replace(" ", "").replace("_", "").replace("-", "")
        if nt in _DAMAGE_TAG_NEEDLES or text_suggests_accident_or_damage(tag):
            return True
    return False


def is_accident_or_damaged_listing(
    *,
    title: str | None = None,
    text_blobs: Sequence[str | None] | None = None,
    feature_keys: Sequence[str] | None = None,
    flags: Mapping[str, Any] | None = None,
    special_conditions: object = None,
) -> bool:
    """Return True when the listing is clearly accident / heavily damaged stock."""
    if feature_keys_suggest_accident(feature_keys):
        return True
    if flags_suggest_accident(flags, special_conditions=special_conditions):
        return True
    if text_suggests_accident_or_damage(title):
        return True
    if text_blobs:
        for blob in text_blobs:
            if text_suggests_accident_or_damage(blob):
                return True
    return False


def should_skip_accident_listing(
    *,
    title: str | None = None,
    text_blobs: Sequence[str | None] | None = None,
    feature_keys: Sequence[str] | None = None,
    flags: Mapping[str, Any] | None = None,
    special_conditions: object = None,
) -> bool:
    """Ingest gate — skip yielding/upserting clear crash ads."""
    return is_accident_or_damaged_listing(
        title=title,
        text_blobs=text_blobs,
        feature_keys=feature_keys,
        flags=flags,
        special_conditions=special_conditions,
    )
