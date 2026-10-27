from datetime import UTC, datetime
import json
from pathlib import Path

from profligator_api.connectors.base import Connector, payload_checksum
from profligator_api.connectors.public_web import public_profile
from profligator_api.schemas import (
    CanonicalProfile,
    ConnectorDescriptor,
    ConnectorMode,
    ConnectorPage,
    NormalizedRecord,
    Platform,
    ProfileSnapshot,
)


_HOSTS = {
    Platform.LEETCODE: "leetcode.com",
    Platform.GEEKSFORGEEKS: "geeksforgeeks.org",
}


class FixtureConnector(Connector):
    def __init__(self, platform: Platform) -> None:
        if platform not in _HOSTS:
            raise ValueError(f"No fixture connector is defined for {platform}")
        self.platform = platform
        self.descriptor = ConnectorDescriptor(
            platform=platform,
            mode=ConnectorMode.FIXTURE,
            live_data=False,
            notice=(
                "Fixture data only. Set this platform's connector to scraper to collect public profile data."
            ),
        )
        fixture_path = Path(__file__).parent.parent / "fixtures" / f"{platform.value}.json"
        self._fixture = json.loads(fixture_path.read_text())

    async def validate_handle(self, handle_or_url: str) -> CanonicalProfile:
        return public_profile(self.platform, handle_or_url)

    async def fetch_profile(self, profile: CanonicalProfile) -> ProfileSnapshot:
        return ProfileSnapshot(
            profile=profile,
            fetched_at=datetime.now(UTC),
            source_total_solved=len(self._fixture["records"]),
            rating=self._fixture.get("rating"),
            rank=self._fixture.get("rank"),
            history_complete=True,
        )

    async def fetch_solved_records(
        self, profile: CanonicalProfile, cursor: str | None = None
    ) -> ConnectorPage:
        records = []
        for item in self._fixture["records"]:
            record = dict(item)
            record["platform"] = self.platform
            record["source_payload_checksum"] = payload_checksum(item)
            records.append(NormalizedRecord.model_validate(record))
        return ConnectorPage(records=records)
