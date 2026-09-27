from abc import ABC, abstractmethod
from hashlib import sha256
import json

from profligator_api.schemas import (
    CanonicalProfile,
    ConnectorDescriptor,
    ConnectorPage,
    ProfileSnapshot,
)


class ConnectorError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def payload_checksum(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


class Connector(ABC):
    descriptor: ConnectorDescriptor

    @abstractmethod
    async def validate_handle(self, handle_or_url: str) -> CanonicalProfile:
        raise NotImplementedError

    @abstractmethod
    async def fetch_profile(self, profile: CanonicalProfile) -> ProfileSnapshot:
        raise NotImplementedError

    @abstractmethod
    async def fetch_solved_records(
        self, profile: CanonicalProfile, cursor: str | None = None
    ) -> ConnectorPage:
        raise NotImplementedError

    async def fetch_contests(
        self, profile: CanonicalProfile, cursor: str | None = None
    ) -> ConnectorPage:
        return ConnectorPage(records=[])
