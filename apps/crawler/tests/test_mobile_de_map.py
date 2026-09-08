from pathlib import Path

from drivecheck_crawler.adapters.mobile_de import MobileDeAdapter
from drivecheck_crawler.adapters.mobile_de_extract import fields_from_record, list_records_from_html
from drivecheck_crawler.config import CrawlerConfig

FIXTURES = Path(__file__).parent / "fixtures" / "mobile_de"


class _NoopCursors:
    def get(self, _key: str) -> dict:
        return {}

    def set(self, _key: str, _value: dict) -> None:
        return None


def test_adapter_fields_to_dto():
    html = (FIXTURES / "list_de.html").read_text(encoding="utf-8")
    record = list_records_from_html(html)[0]
    fields = fields_from_record(record)
    assert fields is not None
    adapter = MobileDeAdapter(client=None, config=CrawlerConfig(), cursors=_NoopCursors())  # type: ignore[arg-type]
    dto = adapter._fields_to_dto(fields)
    assert dto.source == "mobile_de"
    assert dto.currency == "EUR"
    assert dto.make == "Škoda"
    assert dto.price_czk == 387_500
