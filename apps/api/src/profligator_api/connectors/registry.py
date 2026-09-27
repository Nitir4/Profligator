from profligator_api.config import Settings
from profligator_api.connectors.base import Connector, ConnectorError
from profligator_api.connectors.codeforces import CodeforcesConnector
from profligator_api.connectors.fixtures import FixtureConnector
from profligator_api.schemas import ConnectorDescriptor, Platform


class ConnectorRegistry:
    def __init__(self, settings: Settings) -> None:
        self._connectors: dict[Platform, Connector] = {
            Platform.LEETCODE: FixtureConnector(Platform.LEETCODE),
            Platform.GEEKSFORGEEKS: FixtureConnector(Platform.GEEKSFORGEEKS),
            Platform.CODEFORCES: CodeforcesConnector(
                settings.codeforces_base_url,
                settings.codeforces_min_interval_seconds,
            ),
        }

    def get(self, platform: Platform) -> Connector:
        connector = self._connectors.get(platform)
        if connector is None:
            raise ConnectorError("unsupported_platform", f"Unsupported platform: {platform}")
        return connector

    def descriptors(self) -> list[ConnectorDescriptor]:
        return [connector.descriptor for connector in self._connectors.values()]
