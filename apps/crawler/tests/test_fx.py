import pytest

from drivecheck_crawler.fx import (
    clear_live_rates,
    import_fx_fields,
    normalize_currency,
    rate_to_czk,
    round_czk_to_hundred,
    set_live_rates,
    to_czk,
)


def test_normalize_currency_aliases():
    assert normalize_currency("€") == "EUR"
    assert normalize_currency("kc") == "CZK"
    assert normalize_currency("zl") == "PLN"


def test_round_czk_to_hundred():
    assert round_czk_to_hundred(254941.36) == 254_900
    assert round_czk_to_hundred(254941) == 254_900
    assert round_czk_to_hundred(254_950) == 255_000  # half-up
    assert round_czk_to_hundred(254_949) == 254_900
    assert round_czk_to_hundred(100) == 100
    assert round_czk_to_hundred(50) == 100
    assert round_czk_to_hundred(149) == 100
    assert round_czk_to_hundred(150) == 200


def test_to_czk_native_czk_not_hundred_rounded():
    # Quoted whole koruny stay as-is (not snapped to 100).
    assert to_czk(250_123, "CZK") == 250_123
    assert to_czk(250_000, "CZK") == 250_000


def test_to_czk_fx_rounds_to_hundred():
    assert to_czk(1000, "EUR", rates={"EUR": 25.0}) == 25_000
    # 10197.654 * 25 = 254941.35 → 254900
    assert to_czk(10_197.654, "EUR", rates={"EUR": 25.0}) == 254_900
    assert to_czk(1000, "PLN", rates={"PLN": 5.8}) == 5_800


def test_unknown_currency_raises():
    with pytest.raises(ValueError, match="No CZK rate"):
        rate_to_czk("GBP", rates={"EUR": 25.0})


def test_env_override(monkeypatch):
    clear_live_rates()
    monkeypatch.setenv("FX_CZK_PER_EUR", "24.5")
    # 10 * 24.5 = 245 → nearest 100 = 200
    assert to_czk(10, "EUR") == 200


def test_import_fx_fields_stores_ecb_metadata():
    from datetime import date

    set_live_rates({"EUR": 24.5, "CZK": 1.0}, date(2026, 8, 14))
    try:
        fields = import_fx_fields(1000, "EUR")
        assert fields["price_foreign"] == 1000.0
        assert fields["fx_rate_date"] == date(2026, 8, 14)
        assert fields["fx_czk_per_unit"] == 24.5
        assert import_fx_fields(250_000, "CZK") == {
            "price_foreign": None,
            "fx_rate_date": None,
            "fx_czk_per_unit": None,
        }
    finally:
        clear_live_rates()
