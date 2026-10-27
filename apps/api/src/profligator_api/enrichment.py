"""Enrich persisted solved identities independently of public history windows."""

import asyncio
from collections.abc import Callable
import logging

from sqlalchemy import select

from profligator_api.connectors.base import Connector, ConnectorError, payload_checksum
from profligator_api.database import Database
from profligator_api.models import CodingRecord
from profligator_api.repository import Repository
from profligator_api.schemas import NormalizedRecord, stored_utc_time


logger = logging.getLogger(__name__)
_METADATA_FIELDS = ("title", "difficulty", "topics", "statement")


def normalized(row: CodingRecord, platform: str) -> NormalizedRecord:
    return NormalizedRecord.model_validate({
        **{key: getattr(row, key) for key in NormalizedRecord.model_fields if key != "platform"},
        "platform": platform, "occurred_at": stored_utc_time(row.occurred_at),
    })


async def enrich_profile(database: Database, profile_id: str, connector: Connector, limit: int,
                         *, authorize: Callable[[], None] | None = None) -> dict:
    """Commit history first; optional metadata errors cannot erase it or fail the import.

    Request at most one budget across both new and previously saved questions. If
    a later request fails, reuse earlier successful checks from the persistent cache.
    Apply metadata to current rows so concurrent acceptance updates keep their dates.
    """
    if not getattr(connector, "supports_problem_metadata", False):
        return {"enrichment_status": "unsupported", "metadata_records_written": 0}
    with database.session() as session:
        repository = Repository(session)
        profile = repository.get_profile(profile_id)
        if profile is None:
            return {"enrichment_status": "disconnected", "metadata_records_written": 0}
        rows = list(session.scalars(select(CodingRecord).where(
            CodingRecord.platform_profile_id == profile_id, CodingRecord.kind == "problem",
            CodingRecord.status == "solved",
        ).order_by(CodingRecord.created_at, CodingRecord.id)))
        records = [normalized(row, profile.platform) for row in rows]
        # Browser-imported text should not consume the budget ahead of missing text.
        records.sort(key=lambda row: (bool(row.statement), bool(row.topics), bool(row.difficulty)))
    status, error = "succeeded", None
    try:
        updates = await asyncio.wait_for(connector.enrich_records(records, limit), timeout=60)
    except (ConnectorError, TimeoutError, ValueError) as exc:
        status = "partial"
        error = exc.code if isinstance(exc, ConnectorError) else "metadata_timeout" if isinstance(exc, TimeoutError) else "invalid_problem_metadata"
        # Zero-budget reads make no further provider requests after denial/rate limiting.
        try:
            updates = await connector.enrich_records(records, 0)
        except (ConnectorError, ValueError):
            updates = []
    except Exception:
        logger.exception("Optional problem enrichment failed for profile %s", profile_id)
        status, error, updates = "partial", "metadata_unavailable", []
    if authorize:
        authorize()
    with database.session() as session:
        repository = Repository(session)
        profile = repository.get_profile(profile_id)
        if profile is None:
            return {"enrichment_status": "disconnected", "metadata_records_written": 0}
        changed = []
        for update in updates:
            current = session.scalar(select(CodingRecord).where(
                CodingRecord.platform_profile_id == profile_id, CodingRecord.source_id == update.source_id,
                CodingRecord.kind == "problem", CodingRecord.status == "solved",
            ))
            if current is None:
                continue
            result = normalized(current, profile.platform)
            # The connector cannot add solves or change acceptance evidence here.
            for key in _METADATA_FIELDS:
                value = getattr(update, key)
                if value:
                    setattr(result, key, value)
            result.source_payload_checksum = payload_checksum(result.model_dump(mode="json", exclude={"source_payload_checksum"}))
            changed.append(result)
        written = repository.upsert_records(profile_id, changed)
    return {"enrichment_status": status, "enrichment_error": error, "metadata_records_written": written}
