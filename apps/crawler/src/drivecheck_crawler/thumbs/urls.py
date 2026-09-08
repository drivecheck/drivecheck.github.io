from __future__ import annotations

# Seznam CDN (sdn.cz) blocks bare image URLs with 401; this transform is what
# Sauto itself uses for og:image and is downloadable.
SAUTO_CDN_TRANSFORM = (
    "exf|res,1024,768,1|wrm,/watermark/sauto.png,10,10|jpg,80,,1"
)

# Hotlink / CDN policies differ per marketplace. Prefer the listing page URL for
# Bazos (path-scoped images); otherwise send the portal origin.
_SOURCE_DOWNLOAD_REFERERS: dict[str, str] = {
    "sauto": "https://www.sauto.cz/",
    "bazos": "https://auto.bazos.cz/",
    "tipcars": "https://www.tipcars.com/",
    "autobazar_eu": "https://www.autobazar.eu/cs/",
    "mobile_de": "https://suchen.mobile.de/",
    "autoscout24": "https://www.autoscout24.de/",
}


def absolutize_image_url(url: str | None) -> str | None:
    if not url:
        return None
    value = url.strip()
    if value.startswith("//"):
        value = "https:" + value
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return None


def is_usable_cover_url(url: str | None) -> bool:
    abs_url = absolutize_image_url(url)
    if not abs_url:
        return False
    lower = abs_url.lower()
    if lower.endswith(".svg") or "bazos.svg" in lower or "/kosik.svg" in lower:
        return False
    return True


def guess_bazos_cover_url(external_id: str) -> str | None:
    """Bazos cover path: /img/1/{last3}/{id}.jpg — used when HTML only has logo SVG."""
    eid = external_id.strip()
    if not eid.isdigit():
        return None
    return f"https://www.bazos.cz/img/1/{eid[-3:]}/{eid}.jpg"


def prepare_download_url(url: str) -> str:
    """Rewrite CDN URLs so the remote host actually serves the bytes."""
    abs_url = absolutize_image_url(url) or url
    if "sdn.cz/" in abs_url and "fl=" not in abs_url:
        sep = "&" if "?" in abs_url else "?"
        return f"{abs_url}{sep}fl={SAUTO_CDN_TRANSFORM}"
    return abs_url


def download_referer_for_source(
    source: str,
    *,
    listing_url: str | None = None,
) -> str | None:
    """Referer header for cover-image downloads (get_bytes).

    Bazos often requires the listing URL (same-site path). Other portals use a
    stable origin. Unknown sources fall back to the listing URL when absolute.
    """
    key = (source or "").strip().lower()
    if key == "bazos":
        if listing_url and listing_url.startswith(("http://", "https://")):
            return listing_url
        return _SOURCE_DOWNLOAD_REFERERS["bazos"]
    if key in _SOURCE_DOWNLOAD_REFERERS:
        return _SOURCE_DOWNLOAD_REFERERS[key]
    if listing_url and listing_url.startswith(("http://", "https://")):
        return listing_url
    return None


def resolve_cover_url(*, source: str, external_id: str, image_url: str | None) -> str | None:
    if is_usable_cover_url(image_url):
        return absolutize_image_url(image_url)
    if source == "bazos":
        return guess_bazos_cover_url(external_id)
    return None
