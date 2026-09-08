"""Regression test for the aborted-transaction fallback bug in upsert_listing.

PostgreSQL aborts the current transaction as soon as one statement inside it
fails. If the primary UPSERT_SQL fails (e.g. on an older DB missing a
column), any further statement run on that same connection — including the
legacy fallback INSERT — is rejected with "current transaction is aborted,
commands ignored until end of transaction block" unless the aborted state is
first recovered via a savepoint rollback (or an equivalent rollback with a
safe cursor lifecycle).

This test uses a lightweight fake psycopg-like connection/cursor that
reproduces exactly that aborted-transaction semantics, so it does not need a
live database to prove the bug and its fix.
"""

from __future__ import annotations

from datetime import datetime, timezone

from drivecheck_crawler.models import ListingDTO
from drivecheck_crawler.repository import ListingRepository


class FakeCursor:
    def __init__(self, conn: "FakeConnection") -> None:
        self._conn = conn
        self._last_row: dict | None = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: dict | tuple | None = None) -> None:
        if self._conn.aborted:
            raise RuntimeError(
                "current transaction is aborted, commands ignored until end of transaction block"
            )
        normalized = " ".join(sql.split())
        self._conn.executed.append(normalized)
        if normalized.startswith("SELECT id, price_czk FROM listings"):
            self._last_row = None
        elif "image_url" in normalized:
            # Simulates an older DB schema that is missing the image/title/
            # published_at columns referenced by the primary UPSERT_SQL.
            self._conn.aborted = True
            raise RuntimeError('column "image_url" of relation "listings" does not exist')
        elif normalized.startswith("INSERT INTO listings"):
            assert isinstance(params, dict)
            self._last_row = {
                "id": "fake-listing-id",
                "inserted": True,
                "price_czk": params["price_czk"],
            }
        else:
            self._last_row = None

    def fetchone(self) -> dict | None:
        return self._last_row


class FakeTransaction:
    """Mimics psycopg.Connection.transaction(): a savepoint that rolls back on error."""

    def __init__(self, conn: "FakeConnection") -> None:
        self._conn = conn

    def __enter__(self) -> "FakeTransaction":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            # Real psycopg issues ROLLBACK TO SAVEPOINT here, which clears
            # the aborted flag on the outer transaction, then re-raises.
            self._conn.aborted = False
        return False


class FakeConnection:
    def __init__(self) -> None:
        self.aborted = False
        self.executed: list[str] = []
        self.committed = False

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    def commit(self) -> None:
        self.committed = True


def _make_dto() -> ListingDTO:
    return ListingDTO(
        source="sauto",
        external_id="123",
        url="https://example.test/1",
        category="passenger",
        price_czk=100_000,
        observed_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
    )


def test_upsert_listing_recovers_from_aborted_primary_upsert_and_runs_fallback() -> None:
    repo = ListingRepository("postgresql://unused")
    fake_conn = FakeConnection()
    repo.connect = lambda: fake_conn  # type: ignore[method-assign]

    repo.upsert_listing(_make_dto())

    fallback_ran = any(
        sql.startswith("INSERT INTO listings") and "category" in sql and "image_url" not in sql
        for sql in fake_conn.executed
    )
    assert fallback_ran, "legacy fallback insert should run after the primary upsert fails"

    price_point_ran = any(sql.startswith("INSERT INTO price_points") for sql in fake_conn.executed)
    assert price_point_ran, "later statements must still run once the aborted transaction recovers"

    assert fake_conn.committed
