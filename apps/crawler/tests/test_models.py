from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from drivecheck_crawler.models import ListingDTO


def test_listing_dto_has_no_contact_fields():
    fields = ListingDTO.model_fields
    for banned in ("phone", "email", "seller_name", "contact"):
        assert banned not in fields


def test_listing_dto_requires_price_and_source():
    assert "price_czk" in ListingDTO.model_fields
    assert "source" in ListingDTO.model_fields
    assert "url" in ListingDTO.model_fields


def test_listing_dto_rejects_facebook_source():
    with pytest.raises(ValidationError):
        ListingDTO(
            source="facebook",
            external_id="1",
            url="https://example.com/1",
            price_czk=100_000,
            observed_at=datetime.now(timezone.utc),
        )


def test_listing_dto_accepts_tipcars_source():
    dto = ListingDTO(
        source="tipcars",
        external_id="1",
        url="https://example.com/1",
        price_czk=100_000,
        observed_at=datetime.now(timezone.utc),
    )
    assert dto.source == "tipcars"


def test_listing_dto_accepts_reserved_future_source():
    dto = ListingDTO(
        source="autobazar_eu",
        external_id="1",
        url="https://example.com/1",
        price_czk=100_000,
        observed_at=datetime.now(timezone.utc),
    )
    assert dto.source == "autobazar_eu"
