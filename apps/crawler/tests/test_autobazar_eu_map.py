from pathlib import Path

from drivecheck_crawler.adapters.autobazar_eu import AutobazarEuAdapter
from drivecheck_crawler.adapters.autobazar_eu_extract import (
    fields_from_record,
    list_records_from_html,
    detail_record_from_html,
)
from drivecheck_crawler.config import CrawlerConfig
from drivecheck_crawler.fx import to_czk
from drivecheck_crawler.models import ListingDTO

FIXTURES = Path(__file__).parent / "fixtures" / "autobazar_eu"


class _NoopCursors:
    def get(self, _key: str) -> dict:
        return {}

    def set(self, _key: str, _value: dict) -> None:
        return None


def _adapter(*, fetch_details: bool = False) -> AutobazarEuAdapter:
    config = CrawlerConfig(
        autobazar_eu_fetch_details=fetch_details,
        autobazar_eu_page_size=20,
    )
    return AutobazarEuAdapter(
        client=None, config=config, cursors=_NoopCursors()
    )  # type: ignore[arg-type]


def test_list_record_maps_to_dto_without_pii():
    html = (FIXTURES / "list_osobne_cz.html").read_text(encoding="utf-8")
    records = list_records_from_html(html)
    # First CZ record (SK is second in fixture).
    cz = next(r for r in records if r.get("id") == "AmTestCzOct1")
    dto = _adapter()._record_to_dto(cz)
    assert isinstance(dto, ListingDTO)
    assert dto.source == "autobazar_eu"
    assert dto.external_id == "AmTestCzOct1"
    assert dto.price_czk == to_czk(15_500, "EUR")
    assert dto.currency == "EUR"
    assert dto.seller_type == "dealer"
    assert dto.region == "Brno"
    assert dto.fuel == "Nafta"
    assert "autobazar.eu" in dto.url

    dumped = dto.model_dump()
    blob = str(dumped).casefold()
    assert "777000111" not in blob
    assert "dealer@" not in blob
    assert "ulice" not in blob
    assert "tmbjf7ne5k0123456" not in blob
    assert "redacted" not in blob
    for banned in ("phone", "email", "seller_name", "vin", "street"):
        assert banned not in dumped


def test_sk_record_dropped():
    html = (FIXTURES / "list_osobne_cz.html").read_text(encoding="utf-8")
    sk = next(r for r in list_records_from_html(html) if r.get("id") == "SkSkipId999")
    assert _adapter()._record_to_dto(sk) is None


def test_detail_fields_on_dto():
    html = (FIXTURES / "detail_octavia.html").read_text(encoding="utf-8")
    record = detail_record_from_html(html)
    assert record is not None
    fields = fields_from_record(record)
    assert fields is not None
    dto = _adapter()._fields_to_dto(fields)
    assert dto.make == "Škoda"
    assert dto.year == 2019
    assert dto.mileage_km == 148_500
    assert "TMBJF7NE5K0123456" not in str(dto.model_dump())


def test_list_row_skips_detail_when_complete():
    from drivecheck_crawler.adapters.autobazar_eu import _needs_detail_enrich

    html = (FIXTURES / "list_osobne_cz.html").read_text(encoding="utf-8")
    cz = next(r for r in list_records_from_html(html) if r.get("id") == "AmTestCzOct1")
    dto = _adapter()._record_to_dto(cz)
    assert dto is not None
    # List fixture has year/km/fuel — enrich would be a no-op when enabled.
    assert dto.year is not None and dto.mileage_km is not None and dto.fuel is not None
    assert _needs_detail_enrich(dto) is False
