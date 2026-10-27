"""Cache only public problem metadata, independently of candidate history."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from profligator_api.database import Database
from profligator_api.models import ProblemMetadata


@dataclass(frozen=True)
class MetadataEntry:
    checked_at: float
    payload: dict | None


class MetadataStore(Protocol):
    def load(self, provider: str, source_ids: list[str]) -> dict[str, MetadataEntry]: ...
    def save(self, provider: str, source_id: str, entry: MetadataEntry) -> None: ...


class DatabaseMetadataStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def load(self, provider: str, source_ids: list[str]) -> dict[str, MetadataEntry]:
        entries = {}
        with self.database.session() as session:
            for start in range(0, len(source_ids), 500):
                rows = session.scalars(select(ProblemMetadata).where(
                    ProblemMetadata.provider == provider,
                    ProblemMetadata.source_id.in_(source_ids[start:start + 500]),
                ))
                for row in rows:
                    checked = row.checked_at
                    if checked.tzinfo is None:
                        checked = checked.replace(tzinfo=UTC)
                    entries[row.source_id] = MetadataEntry(checked.timestamp(), row.payload)
        return entries

    def save(self, provider: str, source_id: str, entry: MetadataEntry) -> None:
        # Atomic upserts support independent workers; an older result cannot
        # overwrite a newer check. Provider request limiting remains separate.
        insert = sqlite_insert if self.database.engine.dialect.name == "sqlite" else pg_insert
        statement = insert(ProblemMetadata).values(
            provider=provider, source_id=source_id, payload=entry.payload,
            checked_at=datetime.fromtimestamp(entry.checked_at, UTC),
        )
        statement = statement.on_conflict_do_update(
            index_elements=[ProblemMetadata.provider, ProblemMetadata.source_id],
            set_={"payload": statement.excluded.payload, "checked_at": statement.excluded.checked_at},
            where=ProblemMetadata.checked_at <= statement.excluded.checked_at,
        )
        with self.database.session() as session:
            session.execute(statement)
