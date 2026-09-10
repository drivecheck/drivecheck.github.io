from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from drivecheck_crawler.adapters.base import SourceAdapter
from drivecheck_crawler.adapters.bazos_extract import clean_region, extract_fields
from drivecheck_crawler.config import CrawlerConfig
from drivecheck_crawler.cursors import CrawlCursorStore
from drivecheck_crawler.http_client import RateLimitedClient
from drivecheck_crawler.listing_quality import should_reject_listing
from drivecheck_crawler.models import ListingDTO
from drivecheck_crawler.normalize import (
    extract_features_from_text,
    map_seller_type,
    now_utc,
    parse_price_czk,
)
from drivecheck_crawler.thumbs.urls import (
    absolutize_image_url,
    guess_bazos_cover_url,
    is_usable_cover_url,
)

logger = logging.getLogger(__name__)

BAZOS_BASE = "https://auto.bazos.cz"
# Personal-car brand paths only (skip utilities / parts).
BAZOS_BRANDS = [
    "alfa",
    "audi",
    "bmw",
    "chevrolet",
    "citroen",
    "dacia",
    "fiat",
    "ford",
    "honda",
    "hyundai",
    "kia",
    "mazda",
    "mercedes",
    "mitsubishi",
    "nissan",
    "opel",
    "peugeot",
    "renault",
    "seat",
    "skoda",
    "suzuki",
    "toyota",
    "volkswagen",
    "volvo",
    "ostatni",
]

BRAND_LABELS = {
    "alfa": "Alfa Romeo",
    "mercedes": "Mercedes-Benz",
    "skoda": "Škoda",
    "volkswagen": "Volkswagen",
    "ostatni": None,
}


class BazosAdapter(SourceAdapter):
    source = "bazos"

    def __init__(
        self,
        client: RateLimitedClient,
        config: CrawlerConfig,
        cursors: CrawlCursorStore,
    ) -> None:
        self._client = client
        self._config = config
        self._cursors = cursors

    def iter_listings(self, *, max_pages: int) -> Iterator[ListingDTO]:
        cursor = self._cursors.get("bazos")
        brand_idx = int(cursor.get("brand_idx", 0)) % len(BAZOS_BRANDS)
        offset = int(cursor.get("offset", 0))
        pages = 0

        while pages < max_pages:
            brand = BAZOS_BRANDS[brand_idx]
            list_url = f"{BAZOS_BASE}/{brand}/" if offset == 0 else f"{BAZOS_BASE}/{brand}/{offset}/"
            html = self._client.get_text(list_url, referer=BAZOS_BASE)
            links = self._extract_listing_links(html)

            if not links:
                brand_idx = (brand_idx + 1) % len(BAZOS_BRANDS)
                offset = 0
                self._cursors.set("bazos", {"brand_idx": brand_idx, "offset": offset})
                pages += 1
                continue

            for path in links:
                detail_url = urljoin(BAZOS_BASE, path)
                dto = self._fetch_detail(detail_url, brand=brand)
                if dto is not None:
                    yield dto

            offset += self._config.bazos_page_size
            pages += 1
            # Heuristic: empty/short next page handled next loop; rotate brand after ~25 pages
            if offset >= 500:
                brand_idx = (brand_idx + 1) % len(BAZOS_BRANDS)
                offset = 0
            self._cursors.set("bazos", {"brand_idx": brand_idx, "offset": offset, "brand": brand})

    @staticmethod
    def _table_value(soup: BeautifulSoup, label: str) -> str | None:
        """Read value cell for a Bazos detail-table label (`Cena:` / `Lokalita:`)."""
        pattern = re.compile(rf"^\s*{re.escape(label)}\s*:?\s*$", re.I)
        for node in soup.find_all(string=pattern):
            parent = node.parent
            if parent is None:
                continue
            if parent.name == "td":
                sibling = parent.find_next_sibling("td")
                if sibling:
                    value = sibling.get_text(" ", strip=True)
                    if value:
                        return value
            # Some rows put "Lokalita: 719 00 Ostrava" in one cell/tr.
            row_text = parent.get_text(" ", strip=True) if parent.name == "tr" else None
            if not row_text and parent.parent and parent.parent.name == "tr":
                row_text = parent.parent.get_text(" ", strip=True)
            if row_text:
                m = re.match(rf"^\s*{re.escape(label)}\s*:?\s*(.+)$", row_text, re.I)
                if m and m.group(1).strip():
                    return m.group(1).strip()
        return None

    def _extract_listing_links(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        links: list[str] = []
        for a in soup.select('a[href*="/inzerat/"]'):
            href = a.get("href") or ""
            if re.search(r"/inzerat/\d+/", href):
                links.append(href)
        # preserve order, unique
        return list(dict.fromkeys(links))

    def _fetch_detail(self, url: str, *, brand: str) -> ListingDTO | None:
        html = self._client.get_text(url, referer=f"{BAZOS_BASE}/{brand}/")
        soup = BeautifulSoup(html, "lxml")
        # Drop contact UI blocks before any text extraction.
        for bad in soup.select(".teldetail, a[href^=tel], a[href^=mailto]"):
            bad.decompose()

        m = re.search(r"/inzerat/(\d+)/", url)
        if not m:
            return None
        external_id = m.group(1)

        # Title often in <h1 class="nadpis"> or similar
        title_el = (
            soup.select_one("h1.nadpisdetail")
            or soup.select_one("h1.nadpis")
            or soup.select_one("h1")
        )
        title = title_el.get_text(" ", strip=True) if title_el else ""
        # Description used only in-memory for field/feature extraction — never persisted.
        popis_el = soup.select_one(".popisdetail") or soup.select_one(".popis")
        popis = popis_el.get_text(" ", strip=True) if popis_el else ""
        page_text = f"{title}\n{popis}"

        # Price — structured "Cena:" row (label often includes trailing colon)
        price = parse_price_czk(self._table_value(soup, "Cena") or "")
        if price is None:
            pm = re.search(r"Cena:\s*([\d\s.]+)\s*Kč", soup.get_text("\n", strip=True), re.I)
            if pm:
                price = parse_price_czk(pm.group(1))
        if price is None:
            return None

        fields = extract_fields(page_text)

        quality = should_reject_listing(
            title=title,
            popis=popis,
            price_czk=price,
            year=fields.year,
            mileage_km=fields.mileage_km,
            url=url,
        )
        if quality is not None:
            logger.info(
                "bazos skip listing id=%s reason=%s title=%r price=%s",
                external_id,
                quality.reason,
                (title or "")[:120],
                price,
            )
            self._soft_hide_parts_listing(external_id)
            return None

        # Region from title suffix " - Mělník" or Lokalita table row (name only, no PII).
        region = None
        tm = re.search(r"\-\s*([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][^|]{1,40})\s*\|\s*Bazoš", title, re.I)
        if tm:
            region = clean_region(tm.group(1))
        if not region:
            region = clean_region(self._table_value(soup, "Lokalita"))

        make = BRAND_LABELS.get(brand, brand.capitalize() if brand != "ostatni" else None)
        model = None
        if title:
            model = re.split(r"\s[-–|]\s", title, maxsplit=1)[0].strip()
            if make and model.lower().startswith(str(make).lower()):
                model = model[len(str(make)) :].strip(" -–,")

        seller_type = map_seller_type(premise=None, text_hints=f"{title} {popis[:200]}")
        features = extract_features_from_text(f"{title} {popis[:500]}")

        # Remove contact-looking nodes from consideration (defense in depth)
        for bad in soup.select("a[href^=tel], a[href^=mailto]"):
            bad.decompose()

        image_url = _extract_cover_image_url(soup, external_id)

        return ListingDTO(
            source="bazos",
            external_id=external_id,
            url=url.split("?")[0],
            make=make,
            model=model or None,
            year=fields.year,
            mileage_km=fields.mileage_km,
            fuel=fields.fuel,
            transmission=fields.transmission,
            drive=fields.drive,
            power_kw=fields.power_kw,
            displacement_cc=fields.displacement_cc,
            body=fields.body,
            seller_type=seller_type,
            region=region,
            price_czk=price,
            feature_keys=features,
            image_url=image_url,
            title=title or None,
            observed_at=now_utc(),
        )

    def _soft_hide_parts_listing(self, external_id: str) -> None:
        """If a parts ad was ingested earlier, mark status=removed (no DELETE)."""
        try:
            from drivecheck_crawler.repository import ListingRepository

            ListingRepository(self._config.database_url).mark_listings_removed(
                "bazos", [external_id]
            )
        except Exception:
            logger.debug(
                "bazos could not soft-hide parts listing id=%s",
                external_id,
                exc_info=True,
            )


def _extract_cover_image_url(soup: BeautifulSoup, external_id: str) -> str | None:
    """Prefer real listing photos; never return site logo SVG."""
    candidates: list[str] = []
    for img in soup.select("img.carousel-cell-image, img.obrazekflithumb"):
        for attr in ("data-flickity-lazyload", "src", "data-src"):
            raw = img.get(attr)
            if isinstance(raw, str) and raw.strip():
                candidates.append(raw.strip())
                break
    for raw in candidates:
        url = absolutize_image_url(raw)
        if not url or not is_usable_cover_url(url):
            continue
        if "/img/" in url:
            return url
    return guess_bazos_cover_url(external_id)
