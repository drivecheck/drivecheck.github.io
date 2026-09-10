"""Ingest gate: parts, leasing/subscription, and field sanity — never upsert junk."""

from __future__ import annotations

from drivecheck_crawler.listing_quality import should_reject_listing


def _reason(
    title: str | None,
    *,
    popis: str | None = None,
    price: int | None = None,
    year: int | None = None,
    mileage_km: int | None = None,
    flags: dict | None = None,
) -> str | None:
    reject = should_reject_listing(
        title=title,
        popis=popis,
        price_czk=price,
        year=year,
        mileage_km=mileage_km,
        flags=flags,
    )
    return reject.reason if reject else None


def test_reject_operating_lease_title():
    assert _reason("Škoda Octavia 1.5 TSI operativní leasing", price=8_900)


def test_reject_operak_and_predplatne():
    assert _reason("Golf 8 operák 7900 Kč/měsíc", price=7_900)
    assert _reason("Octavia předplatné Auto ESA", price=9_900)
    assert _reason("Superb na splátky formou operáku", price=12_000)


def test_reject_monthly_price_as_lease():
    assert _reason("BMW 320d xDrive, 8 900 Kč / měsíc", price=8_900)
    assert _reason("Audi A4 Avant Leasingrate 299 €/Monat", price=7_500)


def test_reject_sauto_operating_lease_flag():
    assert _reason(
        "Škoda Octavia 2.0 TDI",
        price=289_000,
        flags={"operating_lease": True},
    )


def test_keep_sale_with_financing_option():
    title = "Škoda Octavia 2.0 TDI 110 kW Combi"
    popis = "Najeto 185000 km. Možnost leasingu, financování možné."
    assert _reason(title, popis=popis, price=289_000, year=2016, mileage_km=185_000) is None


def test_keep_sale_lze_na_splatky():
    title = "Hyundai i30 1.6 CRDi r.v. 2017 112000 km"
    popis = "Lze na splátky, úvěr od banky."
    assert _reason(title, popis=popis, price=189_000, year=2017, mileage_km=112_000) is None


def test_reject_parts_via_quality_gate():
    reason = _reason("ALU kola Škoda Octavia 16\"", price=8_000)
    assert reason is not None
    assert reason.startswith("parts:")


def test_reject_implausible_year():
    assert _reason("Škoda Octavia 1.9 TDI", price=80_000, year=1985)
    assert _reason("Škoda Octavia 1.9 TDI", price=80_000, year=2099)


def test_reject_implausible_mileage():
    assert _reason("Škoda Octavia 1.9 TDI", price=80_000, year=2010, mileage_km=4_000_000)


def test_reject_implausible_price():
    assert _reason("Škoda Octavia 1.9 TDI", price=400, year=2010, mileage_km=180_000)
    assert _reason("Škoda Octavia 1.9 TDI", price=80_000_000, year=2010, mileage_km=180_000)


def test_keep_incomplete_but_plausible_car():
    """Bazos often lacks year/km — missing fields must not reject a real car."""
    assert (
        _reason("Škoda Octavia 2.0 TDI 110 kW Combi", price=289_000) is None
    )


def test_empty_title_not_rejected_as_parts_or_lease():
    assert _reason(None, price=100_000) is None
    assert _reason("", price=100_000) is None
