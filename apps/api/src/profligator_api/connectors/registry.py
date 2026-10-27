from profligator_api.config import Settings
from profligator_api.connectors.base import Connector, ConnectorError
from profligator_api.connectors.codeforces import CodeforcesConnector
from profligator_api.connectors.fixtures import FixtureConnector
from profligator_api.connectors.aggregation_service import AggregationServiceConnector
from profligator_api.connectors.leetcode import LeetCodeConnector
from profligator_api.connectors.geeksforgeeks import GeeksForGeeksConnector
from profligator_api.connectors.metadata import MetadataStore
from profligator_api.schemas import ConnectorDescriptor, Platform


class ConnectorRegistry:
    def __init__(self, settings: Settings, *, metadata_store: MetadataStore | None = None) -> None:
        self._connectors: dict[Platform, Connector] = {
            Platform.LEETCODE: LeetCodeConnector(settings.scraper_min_interval_seconds, settings.scraper_statement_limit,
                                               metadata_store=metadata_store, calendar_year_limit=settings.scraper_calendar_year_limit,
                                               collect_contests=settings.leetcode_collect_contests)
            if settings.leetcode_connector == "scraper" else FixtureConnector(Platform.LEETCODE),
            Platform.GEEKSFORGEEKS: GeeksForGeeksConnector(settings.scraper_min_interval_seconds, settings.scraper_statement_limit,
                                                         metadata_store=metadata_store)
            if settings.geeksforgeeks_connector == "scraper" else FixtureConnector(Platform.GEEKSFORGEEKS),
            Platform.CODEFORCES: CodeforcesConnector(
                settings.codeforces_base_url,
                settings.codeforces_min_interval_seconds,
                metadata_store=metadata_store,
            ),
        }
        if settings.aggregation_service_url:
            for platform in (Platform.LEETCODE, Platform.GEEKSFORGEEKS):
                self._connectors[platform] = AggregationServiceConnector(platform, settings.aggregation_service_url)

    def get(self, platform: Platform) -> Connector:
        connector = self._connectors.get(platform)
        if connector is None:
            raise ConnectorError("unsupported_platform", f"Unsupported platform: {platform}")
        return connector

    def descriptors(self) -> list[ConnectorDescriptor]:
        return [connector.descriptor for connector in self._connectors.values()]
