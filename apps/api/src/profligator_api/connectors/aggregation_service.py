"""Adapter for an operator-controlled, normalized public-data service.

The contract is documented in docs/backend-design.md. The API never accepts a
service URL from a candidate and never fetches a URL embedded in source records.
"""

from urllib.parse import quote

import httpx
from pydantic import ValidationError

from profligator_api.connectors.base import ConnectorError
from profligator_api.connectors.fixtures import FixtureConnector
from profligator_api.schemas import (
    CanonicalProfile, ConnectorDescriptor, ConnectorMode, ConnectorPage, Platform, ProfileSnapshot,
)


class AggregationServiceConnector(FixtureConnector):
    def __init__(self, platform: Platform, base_url: str, *, transport: httpx.AsyncBaseTransport | None = None):
        super().__init__(platform)
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.descriptor = ConnectorDescriptor(
            platform=platform, mode=ConnectorMode.AGGREGATOR, live_data=True,
            notice="Uses the configured public-data service; coverage is reported by the provider.",
        )

    async def _get(self, profile: CanonicalProfile, suffix: str = "", **params) -> dict:
        path = f"{self.base_url}/v1/{self.platform.value}/profiles/{quote(profile.handle, safe='')}{suffix}"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=5), transport=self.transport) as client:
                response = await client.get(path, params=params)
                if response.status_code == 404:
                    raise ConnectorError("profile_not_found", "Public coding profile not found")
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Expected an object")
                return payload
        except httpx.HTTPError as exc:
            raise ConnectorError("aggregation_service_unavailable", "Public-data service unavailable", retryable=True) from exc
        except ValueError as exc:
            raise ConnectorError("invalid_provider_response", "Public-data service returned invalid data") from exc

    async def fetch_profile(self, profile: CanonicalProfile) -> ProfileSnapshot:
        try:
            result = ProfileSnapshot.model_validate(await self._get(profile))
        except ValidationError as exc:
            raise ConnectorError("invalid_provider_response", "Invalid public profile snapshot") from exc
        if result.profile.platform != self.platform or result.profile.handle.casefold() != profile.handle.casefold():
            raise ConnectorError("invalid_provider_response", "Provider returned a different coding profile")
        return result

    async def _records(self, profile: CanonicalProfile, kind: str, cursor: str | None) -> ConnectorPage:
        try:
            result = ConnectorPage.model_validate(await self._get(profile, "/records", kind=kind, **({"cursor": cursor} if cursor else {})))
        except ValidationError as exc:
            raise ConnectorError("invalid_provider_response", "Invalid public coding records") from exc
        if any(record.platform != self.platform or record.kind.value != kind for record in result.records):
            raise ConnectorError("invalid_provider_response", "Provider returned records for another platform or kind")
        return result

    async def fetch_solved_records(self, profile: CanonicalProfile, cursor: str | None = None) -> ConnectorPage:
        return await self._records(profile, "problem", cursor)

    async def fetch_contests(self, profile: CanonicalProfile, cursor: str | None = None) -> ConnectorPage:
        return await self._records(profile, "contest", cursor)
