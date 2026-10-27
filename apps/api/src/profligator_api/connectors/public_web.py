"""Small, bounded HTTP and parsing helpers for public profile collectors."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from html.parser import HTMLParser
import json
import re
import time
from urllib.parse import urljoin, urlparse
from weakref import WeakKeyDictionary

import httpx

from profligator_api.connectors.base import ConnectorError
from profligator_api.connectors.codeforces import RequestIntervalLimiter
from profligator_api.connectors.metadata import MetadataEntry, MetadataStore
from profligator_api.schemas import CanonicalProfile, Platform


_HANDLE = re.compile(r"^[A-Za-z0-9_.-]{2,64}$")
_SLUG = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
_LIMITERS: WeakKeyDictionary = WeakKeyDictionary()
_METADATA: dict[tuple[str, str], MetadataEntry] = {}


def public_profile(platform: Platform, value: str) -> CanonicalProfile:
    value = value.strip().rstrip("/")
    host = "leetcode.com" if platform == Platform.LEETCODE else "www.geeksforgeeks.org"
    prefix = "u" if platform == Platform.LEETCODE else "profile"
    if "://" in value:
        try:
            parsed = urlparse(value)
            port = parsed.port
        except ValueError as exc:
            raise ConnectorError("invalid_profile_url", "The profile URL is invalid") from exc
        hosts = {"leetcode.com", "www.leetcode.com"} if platform == Platform.LEETCODE else {
            "geeksforgeeks.org", "www.geeksforgeeks.org", "auth.geeksforgeeks.org",
        }
        if (parsed.scheme not in {"http", "https"} or parsed.hostname not in hosts
                or parsed.username or parsed.password or port not in {None, 80, 443}):
            raise ConnectorError("invalid_profile_url", f"Expected a {host} profile URL")
        parts = parsed.path.strip("/").split("/")
        prefixes = {"u"} if platform == Platform.LEETCODE else {"user", "profile"}
        # LeetCode's older /username/ links are still in circulation.
        if platform == Platform.LEETCODE and len(parts) == 1:
            handle = parts[0]
        elif len(parts) == 2 and parts[0] in prefixes:
            handle = parts[1]
        else:
            raise ConnectorError("invalid_profile_url", f"Expected a /{prefix}/{{handle}} URL")
    else:
        handle = value
    if not _HANDLE.fullmatch(handle) or not any(char.isalnum() for char in handle):
        raise ConnectorError("invalid_handle", "The profile handle format is invalid")
    return CanonicalProfile(
        platform=platform, handle=handle,
        canonical_url=f"https://{host}/{prefix}/{handle}/", display_name=handle,
    )


def slug(value: object) -> str:
    if not isinstance(value, str) or not _SLUG.fullmatch(value):
        raise ConnectorError("invalid_provider_response", "Provider returned an invalid problem slug")
    return value


def invalid_response(message: str) -> ConnectorError:
    return ConnectorError("invalid_provider_response", message)


def integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, str)) and str(value).lstrip("-").isdigit():
            return int(value)
    except (ValueError, OverflowError):
        pass
    return None


def timestamp(value: object) -> datetime | None:
    """Accept epochs or explicitly zoned dates; do not guess a naive date's zone."""
    number = integer(value)
    try:
        if number is not None:
            return datetime.fromtimestamp(number, UTC)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(UTC) if parsed.tzinfo is not None else None
    except (ValueError, OverflowError, OSError):
        pass
    return None


def page_start(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not cursor.isascii() or not cursor.isdigit() or len(cursor) > 8:
        raise ConnectorError("invalid_pagination", "Invalid collector cursor")
    return int(cursor)


def source_local_time(value: object) -> str | None:
    """Keep explicitly supplied clock fields when their time zone is unknown."""
    if isinstance(value, str) and len(value) <= 32:
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None and "T" in value.replace(" ", "T"):
                return parsed.isoformat(timespec="seconds")
        except ValueError:
            pass
    return None


class _HTML(HTMLParser):
    def __init__(self, base_url: str | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.scripts: list[tuple[dict, str]] = []
        self.text: list[str] = []
        self._script: dict | None = None
        self._parts: list[str] = []
        self._hidden = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "script":
            self._script, self._parts = dict(attrs), []
        elif tag in {"style", "noscript"}:
            self._hidden += 1
        elif self._script is None and not self._hidden:
            if tag in {"br", "p", "div", "li", "pre", "tr", "h1", "h2", "h3"}:
                self.text.append("\n")
            elif tag == "sup":
                self.text.append("^(")
            elif tag == "sub":
                self.text.append("_(")
            elif tag in {"td", "th"}:
                self.text.append(" | ")
            elif tag == "img":
                attributes = dict(attrs)
                source = attributes.get("src", "")
                if self.base_url and source:
                    source = urljoin(self.base_url, source)
                self.text.append(f" [image: {source} {attributes.get('alt', '')}] ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._script is not None:
            self.scripts.append((self._script, "".join(self._parts)))
            self._script = None
        elif tag in {"style", "noscript"}:
            self._hidden = max(0, self._hidden - 1)
        elif self._script is None and not self._hidden:
            if tag in {"p", "div", "li", "pre", "tr", "h1", "h2", "h3"}:
                self.text.append("\n")
            elif tag in {"sup", "sub"}:
                self.text.append(")")

    def handle_data(self, data: str) -> None:
        if self._script is not None:
            self._parts.append(data)
        elif not self._hidden:
            self.text.append(data)


def statement_text(html: object, *, base_url: str | None = None) -> str | None:
    if not isinstance(html, str) or not html.strip():
        return None
    if re.search(r"<(svg|canvas|math)\b", html, re.I):
        # These require a structural representation; dropping their geometry or
        # mathematical layout could make unrelated tasks look exactly identical.
        return None
    parser = _HTML(base_url)
    parser.feed(html)
    text = "\n".join(re.sub(r"[ \t\r\f\v]+", " ", line).strip()
                     for line in "".join(parser.text).splitlines() if line.strip())
    if re.fullmatch(r"(?:authentication required|please (?:sign|log) in|(?:sign|log) in to (?:view|continue|access)(?: this problem)?)[.!\s]*", text, re.I):
        return None
    # Truncating two long statements could create a false exact match.
    return text if text and len(text) <= 50000 else None


def embedded_json(html: str) -> list[object]:
    """Read Next.js JSON and Flight chunks as data, never execute JavaScript."""
    parser = _HTML()
    parser.feed(html)
    documents: list[object] = []
    chunks: list[str] = []
    for attrs, content in parser.scripts:
        if attrs.get("id") == "__NEXT_DATA__":
            try:
                documents.append(json.loads(content))
            except ValueError:
                raise invalid_response("Provider returned malformed page data")
        for match in re.finditer(r"self\.__next_f\.push\((\[.*?\])\)\s*;?", content, re.S):
            try:
                item = json.loads(match[1])
                if len(item) == 2 and item[0] == 1 and isinstance(item[1], str):
                    chunks.append(item[1])
            except (ValueError, TypeError):
                continue
    # Flight records may be split between script tags. Only JSON records are useful here.
    for line in "".join(chunks).splitlines():
        _, separator, value = line.partition(":")
        if separator and value.startswith(("[", "{")):
            try:
                documents.append(json.loads(value))
            except ValueError:
                continue
    return documents


def objects(document: object):
    stack = [document]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            yield value
            stack.extend(reversed(list(value.values())))
        elif isinstance(value, list):
            stack.extend(reversed(value))


class PublicWebClient:
    def __init__(self, provider: str, hosts: set[str], interval: float, *,
                 transport: httpx.AsyncBaseTransport | None = None,
                 metadata_store: MetadataStore | None = None) -> None:
        self.provider, self.hosts, self.interval = provider, hosts, interval
        self.transport = transport
        self.metadata_store = metadata_store
        self.coordination_database = getattr(metadata_store, "database", None)
        self._local_limiter = RequestIntervalLimiter(interval)
        self._local_metadata: dict[tuple[str, str], MetadataEntry] = {}

    async def request(self, method: str, url: str, *, json_body: dict | None = None,
                      optional: bool = False) -> httpx.Response | None:
        loop = asyncio.get_running_loop()
        if self.transport is not None:
            limiter = self._local_limiter
        else:
            # Registries are created for each job; share the throttle across those jobs.
            limiters = _LIMITERS.setdefault(loop, {})
            limiter = limiters.setdefault(self.provider, RequestIntervalLimiter(self.interval))
            limiter.interval_seconds = max(limiter.interval_seconds, self.interval)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20, connect=5), transport=self.transport,
            headers={"User-Agent": "Profligator/0.1 (public coding profile collector)",
                     "Accept": "application/json, text/html", "Referer": "https://" + sorted(self.hosts)[-1] + "/"},
        ) as client:
            for _ in range(4):
                parsed = urlparse(url)
                if (parsed.scheme != "https" or parsed.hostname not in self.hosts
                        or parsed.username or parsed.password or parsed.port not in {None, 443}):
                    raise ConnectorError("provider_redirect_blocked", "Provider redirected outside its public site")
                await self.pace()
                await limiter.wait()
                try:
                    async with client.stream(method, url, json=json_body) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            if method != "GET" or "location" not in response.headers:
                                raise ConnectorError("provider_redirect_blocked", "Unexpected provider redirect")
                            url = urljoin(url, response.headers["location"])
                            continue
                        if optional and response.status_code in {401, 404, 410}:
                            return None
                        codes = {401: ("provider_access_denied", "requires authentication"),
                                 403: ("provider_access_denied", "declined public access"),
                                 429: ("provider_rate_limited", "rate limited collection; try a later sync"),
                                 404: ("profile_not_found", "profile was not found")}
                        if response.status_code in codes:
                            code, message = codes[response.status_code]
                            # These responses stop the job. No immediate retry or alternate identity.
                            raise ConnectorError(code, f"{self.provider} {message}")
                        if response.is_error:
                            raise ConnectorError("provider_http_error", f"{self.provider} returned HTTP {response.status_code}",
                                                 retryable=response.status_code >= 500)
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > 5_000_000:
                                raise invalid_response(f"{self.provider} response exceeded the collection limit")
                        # aiter_bytes already decompresses. Reusing Content-Encoding here
                        # would make httpx try to decompress the normalized body twice.
                        headers = dict(response.headers)
                        headers.pop("content-encoding", None)
                        headers.pop("content-length", None)
                        return httpx.Response(response.status_code, headers=headers,
                                              content=bytes(body), request=response.request)
                except httpx.TimeoutException as exc:
                    raise ConnectorError("provider_timeout", f"{self.provider} timed out", retryable=True) from exc
                except httpx.HTTPError as exc:
                    raise ConnectorError("provider_http_error", f"{self.provider} could not be reached", retryable=True) from exc
        raise ConnectorError("provider_redirect_blocked", "Provider returned too many redirects")

    async def pace(self):
        if self.coordination_database is not None and self.transport is None:
            from profligator_api.coordination import pace_request
            await pace_request(self.coordination_database, "source:" + self.provider.lower(), self.interval)

    def json(self, response: httpx.Response) -> dict:
        try:
            data = response.json()
        except ValueError as exc:
            raise invalid_response(f"{self.provider} returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise invalid_response(f"{self.provider} returned an unexpected response")
        return data

    async def problem_metadata(
        self, source_ids: list[str], loader: Callable[[str], Awaitable[dict | None]], limit: int,
    ) -> dict[str, dict | None]:
        """Spend the request budget on unchecked problems, then oldest stale ones.

        Known unavailable statements also count as checks, so they cannot prevent
        later problems from being enriched. Cache hits never consume the budget.
        """
        keys = list(dict.fromkeys(source_ids))
        cache = self._local_metadata if self.transport is not None else _METADATA
        # Persistent stores are authoritative and isolated from other databases.
        entries = self.metadata_store.load(self.provider, keys) if self.metadata_store else {
            key: cache[(self.provider, key)] for key in keys if (self.provider, key) in cache
        }
        now = time.time()
        pending = [key for key in keys if key not in entries or now - entries[key].checked_at >= 86400]
        pending.sort(key=lambda key: entries[key].checked_at if key in entries else float('-inf'))
        for key in pending[:max(0, limit)]:
            data = await loader(key)
            entry = MetadataEntry(time.time(), data)
            if self.metadata_store:
                self.metadata_store.save(self.provider, key, entry)
            else:
                if len(cache) >= 1000:
                    cache.pop(next(iter(cache)))
                cache[(self.provider, key)] = entry
            entries[key] = entry
        # Retain previously observed public metadata while stale checks wait.
        return {key: entry.payload for key, entry in entries.items()}
