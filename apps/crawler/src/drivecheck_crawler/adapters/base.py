from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from drivecheck_crawler.models import ListingDTO


class SourceAdapter(ABC):
    """Marketplace adapter — discover via iter_listings; removals via probe job."""

    source: str

    @abstractmethod
    def iter_listings(self, *, max_pages: int) -> Iterator[ListingDTO]:
        raise NotImplementedError

    def fetch_listing(self, external_id: str) -> ListingDTO:
        raise NotImplementedError(
            "Optional detail fetch; existence checks live in drivecheck_crawler.probe"
        )
