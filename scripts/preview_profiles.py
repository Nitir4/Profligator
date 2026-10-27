#!/usr/bin/env python3
"""Load saved public collector output into a separate local preview database."""

import argparse
import json
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api/src"))

from profligator_api.database import Database
from profligator_api.repository import Repository
from profligator_api.schemas import CalendarCollection, ConnectorMode, NormalizedRecord, ProfileSnapshot
from profligator_api.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("samples", type=Path, nargs="+", help="JSON files written by collect_profile.py")
    parser.add_argument("--database", type=Path, default=Path("/tmp/profligator-preview/preview.db"))
    parser.add_argument("--web-url", default="http://localhost:5174")
    args = parser.parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    database = Database(f"sqlite:///{args.database.resolve()}")
    database.initialize()
    previews = []
    try:
        with database.session() as session:
            repository = Repository(session)
            for path in args.samples:
                sample = json.loads(path.read_text())
                snapshot = ProfileSnapshot.model_validate(sample["snapshot"])
                records = [NormalizedRecord.model_validate(record) for record in sample["records"]]
                identity = f"{snapshot.profile.platform.value}_{snapshot.profile.handle}"
                email = f"{identity}@preview.example"
                user = repository.get_user_by_email(email)
                if user is None:
                    user = repository.create_user(email=email, handle=f"demo_{identity}", password_hash=hash_password("PreviewOnly2026!"))
                    user.is_sharing_enabled = True
                    user.share_token = secrets.token_urlsafe(32)
                profile = repository.save_profile(user.id, snapshot.profile, ConnectorMode(sample["connector"]["mode"]), live_data=sample["connector"]["live_data"])
                written = repository.upsert_records(profile.id, records)
                repository.save_snapshot(profile.id, snapshot)
                if sample.get("activity"):
                    repository.save_activity(profile.id, CalendarCollection.model_validate(sample["activity"]))
                run = repository.start_sync(profile.id)
                repository.finish_sync(run, seen=len(records), written=written)
                profile.last_successful_sync = snapshot.fetched_at
                run.finished_at = snapshot.fetched_at
                previews.append({"handle": snapshot.profile.handle, "email": email, "url": f"{args.web_url.rstrip('/')}/p/{user.share_token}", "imported": sum(record.kind.value == "problem" for record in records), "reported": snapshot.source_total_solved})
        (args.database.parent / "profiles.json").write_text(json.dumps(previews, indent=2) + "\n")
        print(json.dumps({"database": str(args.database), "demo_password": "PreviewOnly2026!", "profiles": previews}, indent=2))
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
