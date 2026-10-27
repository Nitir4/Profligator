#!/usr/bin/env python3
"""Collect a public profile to normalized JSON without modifying the application DB."""

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api/src"))

from profligator_api.config import Settings
from profligator_api.connectors import ConnectorError
from profligator_api.connectors.geeksforgeeks import GeeksForGeeksConnector
from profligator_api.connectors.leetcode import LeetCodeConnector
from profligator_api.connectors.metadata import DatabaseMetadataStore
from profligator_api.database import Database


async def collect(args: argparse.Namespace) -> dict:
    settings = Settings()
    connector_type = LeetCodeConnector if args.platform == "leetcode" else GeeksForGeeksConnector
    database = None
    if args.metadata_cache:
        args.metadata_cache.parent.mkdir(parents=True, exist_ok=True)
        database = Database(f"sqlite:///{args.metadata_cache.resolve()}")
        database.initialize()
    try:
        connector = connector_type(
            settings.scraper_min_interval_seconds, args.statement_limit,
            metadata_store=DatabaseMetadataStore(database) if database else None,
            **({"calendar_year_limit": args.calendar_year_limit,
                "collect_contests": getattr(args, "include_contests", False) or settings.leetcode_collect_contests}
               if args.platform == "leetcode" else {}),
        )
        return await collect_records(connector, args.handle)
    finally:
        if database:
            database.dispose()


async def collect_records(connector, handle: str) -> dict:
    profile = await connector.validate_handle(handle)
    snapshot = await connector.fetch_profile(profile)
    records = []
    for method in (connector.fetch_solved_records, connector.fetch_contests):
        cursor = None
        seen = set()
        while True:
            page = await method(snapshot.profile, cursor)
            records.extend(page.records)
            if page.next_cursor is None:
                break
            if page.next_cursor in seen:
                raise ConnectorError("invalid_pagination", "Provider repeated a cursor")
            seen.add(page.next_cursor)
            cursor = page.next_cursor
    activity = await connector.fetch_activity(profile)
    return {"connector": connector.descriptor.model_dump(mode="json"),
            "activity": activity.model_dump(mode="json"),
            "snapshot": snapshot.model_dump(mode="json"),
            "records": [record.model_dump(mode="json") for record in records]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=("leetcode", "geeksforgeeks"))
    parser.add_argument("handle", help="Public handle or profile URL")
    parser.add_argument("--statement-limit", type=int, default=20, help="Maximum problem-page requests (0–50)")
    parser.add_argument("--metadata-cache", type=Path, help="Optional separate SQLite cache; resume enrichment across runs")
    parser.add_argument("--calendar-year-limit", type=int, default=3, help="Maximum calendar year requests (1–10)")
    parser.add_argument("--include-contests", action="store_true", help="Opt in to deferred LeetCode contest statistics")
    parser.add_argument("--output", type=Path, help="Write normalized JSON to this file")
    args = parser.parse_args()
    if not 0 <= args.statement_limit <= 50:
        parser.error("--statement-limit must be between 0 and 50")
    if not 1 <= args.calendar_year_limit <= 10:
        parser.error("--calendar-year-limit must be between 1 and 10")
    try:
        result = asyncio.run(collect(args))
    except ConnectorError as exc:
        print(json.dumps({"error": {"code": exc.code, "message": exc.message}}), file=sys.stderr)
        return 2
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        records = result["records"]
        print(json.dumps({"platform": args.platform, "handle": result["snapshot"]["profile"]["handle"],
                          "source_total_solved": result["snapshot"]["source_total_solved"],
                          "history_complete": result["snapshot"]["history_complete"],
                          "problems": sum(record["kind"] == "problem" for record in records),
                          "contests": sum(record["kind"] == "contest" for record in records),
                          "statements": sum(bool(record["statement"]) for record in records),
                          "timestamped_questions": sum(record["kind"] == "problem" and record["occurred_at"] is not None for record in records),
                          "source_local_question_times": sum(record.get("source_solved_at") is not None for record in records),
                          "activity_status": result["activity"]["status"],
                          "calendar_years": [calendar["year"] for calendar in result["activity"]["calendars"]],
                          "active_days": sum(len(calendar["days"]) for calendar in result["activity"]["calendars"]),
                          "calendar_submissions": sum(day["count"] for calendar in result["activity"]["calendars"] for day in calendar["days"]),
                          "output": str(args.output)}))
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
