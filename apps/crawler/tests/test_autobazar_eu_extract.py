from pathlib import Path

from drivecheck_crawler.adapters.autobazar_eu_extract import (
    fields_from_record,
    is_czech_location,
    list_records_from_html,
    offer_price_amount,
    parse_max_list_page,
    parse_mileage_km,
    detail_record_from_html,
)
from drivecheck_crawler.fx import to_czk
from drivecheck_crawler.normalize import parse_int, parse_money_amount

FIXTURES = Path(__file__).parent / "fixtures" / "autobazar_eu"


def _cz_base(**overrides):
    base = {
        "id": "AmFxTest1",
        "sefName": "skoda-fabia-test",
        "finalPrice": 1700,
        "priceCurrent": 1700,
        "price": 1700,
        "unitPrice": 0,
        "brandValue": "Škoda",
        "carModelValue": "Fabia",
        "yearValue": 2008,
        "mileage": 180_000,
        "locationIds": ["200000000"],
        "location": {
            "name": "Brno",
            "parentNames": ["Česká republika"],
            "parents": ["200000000"],
        },
    }
    base.update(overrides)
    return base


def test_list_records_cz_only_and_max_page():
    html = (FIXTURES / "list_osobne_cz.html").read_text(encoding="utf-8")
    records = list_records_from_html(html)
    assert len(records) == 3
    assert parse_max_list_page(html) == 12

    cz = [r for r in records if is_czech_location(r)]
    sk = [r for r in records if not is_czech_location(r)]
    assert len(cz) == 2
    assert len(sk) == 1

    fields = fields_from_record(cz[0])
    assert fields is not None
    assert fields["external_id"] == "AmTestCzOct1"
    assert fields["price_czk"] == to_czk(15_500, "EUR")
    assert fields["currency"] == "EUR"
    assert fields["region"] == "Brno"
    assert fields["seller_type"] == "dealer"
    assert fields["make"] == "Škoda"
    assert fields["model"] == "Octavia"
    assert fields["year"] == 2019
    assert fields["mileage_km"] == 148_500
    assert fields["power_kw"] == 110
    assert fields["displacement_cc"] == 1968
    assert fields["body"] == "Kombi"

    # SK row must not map when require_czech (default).
    assert fields_from_record(sk[0]) is None

    # Fixture still carries contact noise on user / vin that must be dropped.
    user = cz[0].get("user") or {}
    assert user.get("telephone") or user.get("street")
    assert cz[0].get("vin")

    blob = str(fields).casefold()
    assert "777000111" not in blob
    assert "dealer@" not in blob
    assert "ulice" not in blob
    assert "tmbjf7ne5k0123456" not in blob
    assert "redacted dealer" not in blob


def test_detail_fields_year_mileage_no_pii():
    html = (FIXTURES / "detail_octavia.html").read_text(encoding="utf-8")
    record = detail_record_from_html(html)
    assert record is not None
    assert record.get("vin") == "TMBJF7NE5K0123456"
    assert "777000111" in str(record.get("description") or "")
    fields = fields_from_record(record)
    assert fields is not None
    assert fields["make"] == "Škoda"
    assert fields["year"] == 2019
    assert fields["mileage_km"] == 148_500
    assert fields["published_at"] is not None
    # Description (with PII) is never mapped onto commercial fields.
    assert "description" not in fields

    blob = str(fields).casefold()
    assert "tmbjf7ne5k0123456" not in blob
    assert "777000111" not in blob
    assert "dealer@example.invalid" not in blob
    assert "ulice 12" not in blob


def test_mileage_rejects_dojezd():
    assert parse_mileage_km("dojezd 450 km WLTP") is None
    assert parse_mileage_km("98 000 km") == 98_000
    assert parse_mileage_km(98_000) == 98_000


def test_parse_money_preserves_decimal_eur():
    # Regression: str(2270.98) digit-strip used to yield 227098.
    assert parse_money_amount(2270.98) == 2270.98
    assert parse_money_amount("2 270,98") == 2270.98
    assert parse_int(2270.98) == 2271
    assert parse_int(1700.0) == 1700


def test_offer_price_eur_integer_path():
    amount, currency = offer_price_amount(_cz_base())
    assert currency == "EUR"
    assert amount == 1700
    fields = fields_from_record(_cz_base())
    assert fields is not None
    assert fields["currency"] == "EUR"
    assert fields["price_czk"] == to_czk(1700, "EUR")
    assert fields["price_czk"] == 42_500


def test_offer_price_native_czk_unit_price():
    """unitPrice=1: `price` is already CZK — never multiply by EUR rate."""
    record = _cz_base(
        finalPrice=2270.98,
        priceCurrent=2270.98,
        price=56_000,
        unitPrice=1,
    )
    assert offer_price_amount(record) == (56_000.0, "CZK")
    fields = fields_from_record(record)
    assert fields is not None
    assert fields["currency"] == "CZK"
    # Native CZK: no nearest-100 FX rounding.
    assert fields["price_czk"] == 56_000
    # Poison path would have been parse_int(2270.98)*25 ≈ 5.67M.
    assert fields["price_czk"] < 200_000


def test_offer_price_fractional_eur_without_czk_mirror():
    record = _cz_base(
        finalPrice=2270.98,
        priceCurrent=2270.98,
        price=2270.98,
        unitPrice=0,
    )
    amount, currency = offer_price_amount(record)
    assert currency == "EUR"
    assert amount == 2270.98
    fields = fields_from_record(record)
    assert fields is not None
    assert fields["currency"] == "EUR"
    assert fields["price_czk"] == to_czk(2270.98, "EUR")
    assert fields["price_czk"] == 56_800  # 2270.98 * 25 → nearest 100


def test_explicit_currency_czk_skips_fx():
    record = _cz_base(
        finalPrice=189_990,
        priceCurrent=189_990,
        price=189_990,
        currency="CZK",
        unitPrice=0,
    )
    assert offer_price_amount(record) == (189_990.0, "CZK")
    fields = fields_from_record(record)
    assert fields is not None
    assert fields["currency"] == "CZK"
    assert fields["price_czk"] == 189_990
