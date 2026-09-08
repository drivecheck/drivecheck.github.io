from drivecheck_crawler.prices import resolve_sauto_prices


def test_typical_dealer_price_includes_vat_and_keeps_without_vat() -> None:
    resolved = resolve_sauto_prices(
        price=139_000,
        price_without_vat=114_876,
        price_is_without_vat=False,
        price_is_vat_deductible=True,
    )
    assert resolved is not None
    assert resolved.price_czk == 139_000
    assert resolved.price_without_vat_czk == 114_876
    assert resolved.vat_deductible is True
    assert resolved.price_includes_vat is True


def test_listed_without_vat_is_grossed_up_for_comps() -> None:
    resolved = resolve_sauto_prices(
        price=100_000,
        price_without_vat=100_000,
        price_is_without_vat=True,
        price_is_vat_deductible=True,
    )
    assert resolved is not None
    assert resolved.price_without_vat_czk == 100_000
    assert resolved.price_czk == 121_000
    assert resolved.price_includes_vat is False
    assert resolved.vat_deductible is True


def test_private_price_without_vat_metadata() -> None:
    resolved = resolve_sauto_prices(price=250_000)
    assert resolved is not None
    assert resolved.price_czk == 250_000
    assert resolved.price_without_vat_czk is None
    assert resolved.vat_deductible is None
