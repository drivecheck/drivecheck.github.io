from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Open string validated against registry (enabled + reserved). Facebook blocked.
ListingSource = str
SellerType = Literal["private", "dealer", "unknown"]


class ListingDTO(BaseModel):
    """Commercial listing fields only — never includes contact/PII."""

    source: ListingSource
    external_id: str
    url: str
    category: str = "passenger"
    make: str | None = None
    model: str | None = None
    generation: str | None = None
    trim: str | None = None
    year: int | None = None
    mileage_km: int | None = None
    fuel: str | None = None
    transmission: str | None = None
    drive: str | None = None
    power_kw: int | None = None
    displacement_cc: int | None = None
    body: str | None = None
    seller_type: SellerType | None = None
    region: str | None = None
    price_czk: int
    price_without_vat_czk: int | None = None
    vat_deductible: bool | None = None
    price_includes_vat: bool | None = None
    """Listing currency before FX normalization (price_czk is always CZK)."""
    currency: str = "CZK"
    """Original asking amount in `currency` (for ECB re-quote). Native CZK: null."""
    price_foreign: float | None = None
    fx_rate_date: date | None = None
    fx_czk_per_unit: float | None = None
    feature_keys: list[str] = Field(default_factory=list)
    image_url: str | None = None
    title: str | None = None
    doors: int | None = None
    color: str | None = None
    first_owner: bool | None = None
    service_book: bool | None = None
    country_of_origin: str | None = None
    published_at: datetime | None = None
    observed_at: datetime

    @field_validator("source")
    @classmethod
    def _validate_source(cls, value: str) -> str:
        from drivecheck_crawler.sources import FORBIDDEN_SOURCE_IDS, get_source

        key = (value or "").strip().lower()
        if key in FORBIDDEN_SOURCE_IDS:
            raise ValueError("Facebook / marketplace social sources are forbidden")
        # Accepts enabled + reserved registry ids (future TipCars rows, etc.).
        get_source(key)
        return key
