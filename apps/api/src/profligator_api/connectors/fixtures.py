from datetime import UTC, datetime
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from profligator_api.connectors.base import Connector, ConnectorError, payload_checksum
from profligator_api.schemas import (
    CanonicalProfile,
    ConnectorDescriptor,
    ConnectorMode,
    ConnectorPage,
    NormalizedRecord,
    Platform,
    ProfileSnapshot,
)


_HANDLE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{2,64}$")
_HOSTS = {
    Platform.LEETCODE: "leetcode.com",
    Platform.GEEKSFORGEEKS: "geeksforgeeks.org",
}
_PATH_PREFIXES = {
    Platform.LEETCODE: "/u/",
    Platform.GEEKSFORGEEKS: "/user/",
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
                "Fixture data only. Automated collection is disabled pending an approved "
                "provider integration or written permission."
            ),
        )
        fixture_path = Path(__file__).parent.parent / "fixtures" / f"{platform.value}.json"
        self._fixture = json.loads(fixture_path.read_text())

    async def validate_handle(self, handle_or_url: str) -> CanonicalProfile:
        value = handle_or_url.strip().rstrip("/")
        if "://" in value:
            parsed = urlparse(value)
            host = parsed.netloc.lower().removeprefix("www.")
            if host != _HOSTS[self.platform]:
                raise ConnectorError("invalid_profile_url", f"Expected {_HOSTS[self.platform]}")
            prefix = _PATH_PREFIXES[self.platform]
            if not parsed.path.startswith(prefix):
                raise ConnectorError("invalid_profile_url", f"Expected a {prefix} profile URL")
            handle = parsed.path[len(prefix) :].split("/")[0]
        else:
            handle = value

        if not _HANDLE_PATTERN.fullmatch(handle):
            raise ConnectorError("invalid_handle", "The profile handle format is invalid")

        return CanonicalProfile(
            platform=self.platform,
            handle=handle,
            canonical_url=f"https://{_HOSTS[self.platform]}{_PATH_PREFIXES[self.platform]}{handle}/",
            display_name=handle,
        )

    async def fetch_profile(self, profile: CanonicalProfile) -> ProfileSnapshot:
        return ProfileSnapshot(
            profile=profile,
            fetched_at=datetime.now(UTC),
            source_total_solved=len(self._fixture["records"]),
            rating=self._fixture.get("rating"),
            rank=self._fixture.get("rank"),
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
