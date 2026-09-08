from drivecheck_crawler.live_search import (
    _fuel_key,
    _row_matches_vehicle,
    _title_matches_model,
    _transmission_compatible,
    _transmission_key,
    dto_to_offer,
)


def test_title_matches_model_requires_model_in_title():
    assert _title_matches_model("Škoda Octavia 2.0 TDI", "Octavia")
    assert not _title_matches_model("Škoda Fabia 1.0", "Octavia")


def test_row_matches_vehicle_rejects_stamped_model_mismatch():
    assert _row_matches_vehicle(
        make_name="Škoda",
        model_name="Octavia",
        title="Škoda Octavia Combi",
        want_make="Škoda",
        want_model="Octavia",
    )
    assert not _row_matches_vehicle(
        make_name="Škoda",
        model_name="Octavia",
        title="Škoda Fabia 1.0 TSI",
        want_make="Škoda",
        want_model="Octavia",
    )


def test_fuel_synonyms_and_contradiction():
    assert _fuel_key("Diesel") == "nafta"
    assert _fuel_key("Nafta") == "nafta"
    assert _fuel_key("Benzín") == "benzin"
    assert _row_matches_vehicle(
        make_name="Škoda",
        model_name="Octavia",
        title="Škoda Octavia 2.0 TDI",
        want_make="Škoda",
        want_model="Octavia",
        fuel="Diesel",
        want_fuel="Nafta",
    )
    assert not _row_matches_vehicle(
        make_name="Škoda",
        model_name="Octavia",
        title="Škoda Octavia 1.5 TSI",
        want_make="Škoda",
        want_model="Octavia",
        fuel="Benzín",
        want_fuel="Nafta",
    )
    # Unknown fuel allowed when user specified.
    assert _row_matches_vehicle(
        make_name="Škoda",
        model_name="Octavia",
        title="Škoda Octavia 2.0 TDI",
        want_make="Škoda",
        want_model="Octavia",
        fuel=None,
        want_fuel="Nafta",
    )


def test_transmission_dsg_compatible_with_automatic():
    assert _transmission_key("DSG") == "dsg"
    assert _transmission_key("Automatická") == "automatic"
    assert _transmission_compatible("dsg", "automatic")
    assert not _transmission_compatible("dsg", "manual")
    assert _row_matches_vehicle(
        make_name="Škoda",
        model_name="Octavia",
        title="Škoda Octavia 2.0 TDI",
        want_make="Škoda",
        want_model="Octavia",
        transmission="Automatická",
        want_transmission="DSG",
    )
    assert not _row_matches_vehicle(
        make_name="Škoda",
        model_name="Octavia",
        title="Škoda Octavia 2.0 TDI",
        want_make="Škoda",
        want_model="Octavia",
        transmission="Manuální",
        want_transmission="DSG",
    )


def test_dto_to_offer_keeps_fx_fields():
    offer = dto_to_offer(
        {
            "source": "autoscout24",
            "external_id": "abc",
            "url": "https://example.com",
            "price_czk": 254_900,
            "currency": "EUR",
            "price_foreign": 10_197.65,
            "fx_rate_date": "2026-08-14",
        }
    )
    assert offer["currency"] == "EUR"
    assert offer["priceForeign"] == 10_197.65
    assert offer["fxRateDate"] == "2026-08-14"
    assert offer["priceCzk"] == 254_900
