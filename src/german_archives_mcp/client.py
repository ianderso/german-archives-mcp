"""Polite, cached async HTTP for the DDB's API and three state archives' sites.

Four hosts, each a public service run by others, so the client is a careful
guest:

* **A fixed allowlist.** A request hook refuses any host but
  :data:`ALLOWED_HOSTS`: the DDB's API, the Landesarchiv Baden-Württemberg's
  online finding aids, the Archive in NRW portal and the Landesarchiv NRW's
  image server. That holds for addresses taken from responses too (an image
  link in a DDB record, a viewer link in an NRW hit, a redirect), so nothing a
  site or a model writes can send a request anywhere else. Redirects are
  followed by hand, and only within one host; anything else is reported, never
  followed.
* **Only public addresses, checked where the connection is made.** The
  transport looks each host up itself, refuses it if any address is private,
  loopback, link-local, shared (CGNAT), multicast, reserved or unspecified,
  and connects to the address it checked.
* **Bounded answers.** A JSON, HTML or XML answer over ``MAX_TEXT_BYTES`` or an
  image over ``MAX_IMAGE_BYTES`` is refused as it streams in.
* **One request at a time per host, at least ``min_interval`` apart,** and
  never less than :data:`HOST_FLOORS` says for a host: two seconds for every
  host. A search that runs on an archive's own database waits longer still:
  :data:`SEARCH_FLOORS` holds the Archive in NRW portal's searches ten seconds
  apart.
* **Identical concurrent calls share one request.**
* **Answers are cached on disk,** keyed by the request address, for as many
  days as the caller says. A failure is never cached, and an unreadable entry
  is fetched again. Images are written to the caller's file, never cached.
* **A 429, a 5xx or a dropped connection gets one retry,** honouring
  ``Retry-After`` up to 30 seconds. A timeout is not retried.
* **An honest User-Agent** naming the package, its version and its home.
* **A bot check is reported, never worked around.** A Cloudflare challenge or
  an Anubis proof-of-work page comes back as ``challenge``.
"""

from __future__ import annotations

import asyncio
import email.utils
import hashlib
import ipaddress
import json
import logging
import os
import random
import socket
import time
import uuid
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx

from . import __version__

logger = logging.getLogger("german_archives_mcp.client")

#: Where the project lives; named in the User-Agent so a site can see who calls.
PROJECT_URL = "https://github.com/ianderso/german-archives-mcp"

#: The DDB's API host. Version 2 needs no key.
DDB_HOST = "api.deutsche-digitale-bibliothek.de"

#: The Landesarchiv Baden-Württemberg's online finding aids and image viewer.
LABW_HOST = "www2.landesarchiv-bw.de"

#: The Archive in NRW portal: its keyless search service (``/sufservice``).
NRW_PORTAL_HOST = "www.archive.nrw.de"

#: The Landesarchiv NRW's server for METS files and page images.
NRW_IMAGE_HOST = "www.landesarchiv-nrw.de"

#: Every host a request may go to. Nothing else, whatever a response links to.
ALLOWED_HOSTS = frozenset({DDB_HOST, LABW_HOST, NRW_PORTAL_HOST, NRW_IMAGE_HOST})

#: Least seconds between two requests to a host, whatever the configuration.
HOST_FLOORS: dict[str, float] = {host: 2.0 for host in ALLOWED_HOSTS}

#: Searches that run on an archive's own database, by host: the path prefixes
#: that count as one, and the least seconds between two of them.
SEARCH_FLOORS: dict[str, tuple[tuple[str, ...], float]] = {
    NRW_PORTAL_HOST: (("/sufservice/api/search",), 10.0),
}

#: Longest wait honoured from a ``Retry-After`` header, in seconds.
RETRY_AFTER_CAP = 30.0

#: Redirect hops followed within one host.
MAX_REDIRECTS = 3

#: An image larger than this is not written. A Standesbuch page served at the
#: viewer's full size is under 2 MB.
MAX_IMAGE_BYTES = 60_000_000

#: A JSON or HTML answer larger than this is refused. A DDB record is about
#: 30 KB, a search page of 50 hits under 100 KB, and the Landesarchiv's
#: thumbnail page of a 700-image book about 100 KB.
MAX_TEXT_BYTES = 10_000_000

#: Read timeout for an image download, which the site renders on demand.
DOWNLOAD_TIMEOUT = 120.0

_DAY = 86_400.0

#: The image formats a download may be, and the file suffixes each may be
#: saved under.
IMAGE_SUFFIXES: dict[str, tuple[str, ...]] = {
    "jpeg": (".jpg", ".jpeg"),
    "png": (".png",),
    "gif": (".gif",),
    "tiff": (".tif", ".tiff"),
    "jp2": (".jp2",),
    "webp": (".webp",),
}

#: First bytes of each format. WebP is a RIFF container, so it is matched by
#: its form type at offset 8 as well (see :func:`sniff_format`).
_SIGNATURES = (
    (b"\xff\xd8\xff", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
    (b"\x00\x00\x00\x0cjP  \r\n\x87\n", "jp2"),
)

#: Text that marks a bot-check page served in place of the answer: Anubis's
#: proof-of-work page (seen on the DDB's portal, not its API, 2026-10-11) and
#: Cloudflare's challenge.
_CHALLENGE_MARKS = (
    "making sure you&#39;re not a bot",
    "making sure you're not a bot",
    'id="anubis_challenge"',
    "/.within.website/",
    "cf-chl",
    "<title>just a moment...</title>",
)

#: Shared address space for carrier-grade NAT, which ``ipaddress`` marks
#: neither private nor global on every supported Python.
_SHARED = ipaddress.ip_network("100.64.0.0/10")

#: NAT64's well-known prefix: its last 32 bits are an IPv4 address.
_NAT64 = ipaddress.ip_network("64:ff9b::/96")


class SiteError(RuntimeError):
    """A request a site refused, or one that could not be completed.

    ``code`` says what kind of failure it was: ``no_response`` and
    ``timeout`` (``status`` 0), ``http_error``, ``rate_limited``,
    ``not_json``, ``too_large``, ``redirected`` (``location`` set),
    ``challenge`` (a bot check), ``not_an_image`` or ``extension_mismatch``.
    """

    def __init__(
        self, code: str, detail: str, *, status: int = 0, url: str = "", location: str = ""
    ):
        """Record what failed and where."""
        self.code = code
        self.detail = detail
        self.status = status
        self.url = url
        self.location = location
        super().__init__(f"{url} -> {code} {status or ''}: {detail}".strip())


class HostNotAllowed(RuntimeError):
    """Raised when a request is aimed at a host not on the allowlist."""


class PrivateAddress(HostNotAllowed):
    """Raised at connect time for a host whose name leads to a non-public address."""


def user_agent(contact: str = "") -> str:
    """The User-Agent sent with every request, naming this project."""
    extra = f"; {contact}" if contact else ""
    return f"german-archives-mcp/{__version__} (+{PROJECT_URL}{extra})"


def sniff_format(head: bytes) -> str:
    """Name an image format from its first bytes, or ``"unknown"``.

    The bytes are trusted over the Content-Type: an HTML error page served
    with a 200 must not pass for a page image.
    """
    for signature, name in _SIGNATURES:
        if head.startswith(signature):
            return name
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return "unknown"


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """A JPEG's (width, height) from its frame header, or None if not found."""
    if not data.startswith(b"\xff\xd8"):
        return None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
            i += 1 if marker == 0xFF else 2
            continue
        length = int.from_bytes(data[i + 2 : i + 4], "big")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height = int.from_bytes(data[i + 5 : i + 7], "big")
            width = int.from_bytes(data[i + 7 : i + 9], "big")
            return width, height
        if length < 2:
            return None
        i += 2 + length
    return None


def address_problem(address: str) -> str | None:
    """Why a connection must not go to this IP address, or None if it may.

    Refused, in IPv4 and IPv6: loopback, private, link-local, shared (CGNAT),
    multicast, reserved, unspecified and site-local addresses, anything else
    not globally routable, and an IPv6 address that carries one of those as
    an embedded IPv4 address (IPv4-mapped, 6to4, NAT64).
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return "unreadable"
    if ip.version == 6:
        if ip.ipv4_mapped is not None:
            return "IPv4-mapped"
        embedded = ip.sixtofour
        if embedded is None and ip in _NAT64:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFF_FFFF)
        if embedded is not None and (problem := address_problem(str(embedded))):
            return problem
    checks = (
        ("loopback", ip.is_loopback),
        ("unspecified", ip.is_unspecified),
        ("link-local", ip.is_link_local),
        ("multicast", ip.is_multicast),
        ("private", ip.is_private),
        ("shared (CGNAT)", ip.version == 4 and ip in _SHARED),
        ("reserved", ip.is_reserved),
        ("site-local", ip.version == 6 and ip.is_site_local),
        ("non-global", not ip.is_global),
    )
    return next((name for name, hit in checks if hit), None)


class PublicOnlyBackend(httpcore.AsyncNetworkBackend):
    """A network backend that connects only to public addresses.

    It resolves the host itself, refuses the connection if any address the
    name gives is not public, and then connects to an address it checked,
    never to the name, so the name cannot answer differently in between.
    TLS still verifies the certificate against the host name.
    """

    def __init__(self, inner: httpcore.AsyncNetworkBackend):
        """Wrap the backend that makes the actual connections."""
        self._inner = inner

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        """Look ``host`` up, check every address, and connect to a checked one."""
        addresses = await _look_up(host, port, timeout)
        for address in addresses:
            if problem := address_problem(address):
                logger.warning("refusing %s: it resolves to %s (%s)", host, address, problem)
                raise PrivateAddress(
                    f"refusing to connect to {host}: it resolves to an address that is not "
                    f"public ({problem})"
                )
        error: Exception | None = None
        for address in addresses:
            try:
                return await self._inner.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                error = exc
        raise error or httpcore.ConnectError(f"cannot connect to {host}")

    async def connect_unix_socket(
        self, path: str, timeout: float | None = None, socket_options: Iterable[Any] | None = None
    ) -> httpcore.AsyncNetworkStream:
        """Refuse: every site is reached over TCP."""
        raise HostNotAllowed("refusing a connection to a local socket")

    async def sleep(self, seconds: float) -> None:
        """Defer to the wrapped backend."""
        await self._inner.sleep(seconds)


async def _look_up(host: str, port: int, timeout: float | None) -> list[str]:
    """Every address ``host`` resolves to, in the resolver's order."""
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, port, type=socket.SOCK_STREAM), timeout
        )
    except TimeoutError:
        raise httpcore.ConnectTimeout(f"looking up {host} took too long") from None
    except OSError as exc:
        raise httpcore.ConnectError(f"cannot look up {host}: {exc}") from None
    addresses = list(dict.fromkeys(str(info[4][0]) for info in infos))
    if not addresses:
        raise httpcore.ConnectError(f"{host} has no address")
    return addresses


class PublicOnlyTransport(httpx.AsyncHTTPTransport):
    """httpx's own transport, connecting through :class:`PublicOnlyBackend`.

    httpx takes no network backend as an argument, so the one its connection
    pool made is wrapped in place. Should a future httpx or httpcore move it,
    construction fails rather than run without the check.
    """

    def __init__(self, *, backend: httpcore.AsyncNetworkBackend | None = None, **kwargs: Any):
        """Build the transport; ``backend`` replaces the real network, for tests."""
        super().__init__(**kwargs)
        pool = getattr(self, "_pool", None)
        inner = getattr(pool, "_network_backend", None)
        if not isinstance(pool, httpcore.AsyncConnectionPool) or not isinstance(
            inner, httpcore.AsyncNetworkBackend
        ):
            raise RuntimeError(
                "httpx's connection pool has changed shape; the public-address check "
                "cannot be installed, so no request will be sent"
            )
        pool._network_backend = PublicOnlyBackend(backend or inner)


class ArchiveHttp:
    """Cached, paced async HTTP for the two allowed hosts.

    Parameters
    ----------
    cache_dir : Path
        Directory for cached responses. Created on first write.
    timeout : float, optional
        Per-request timeout in seconds.
    min_interval : float, optional
        Least time between the start of one request to a host and the next.
    contact : str, optional
        Appended to the User-Agent.
    retries : int, optional
        Further attempts after a 429, a 5xx or a dropped connection.
    backoff : float, optional
        Base of the wait between attempts when no ``Retry-After`` is given.
    host_floors : dict, optional
        Least interval per host, whatever ``min_interval`` says. Tests pass {}.
    search_floors : dict, optional
        Least interval between two database searches on a host. Tests pass {}.
    transport : httpx.AsyncBaseTransport, optional
        For tests. The default is a :class:`PublicOnlyTransport`. httpx does
        not apply proxy settings from the environment to a transport it is
        given, which suits the check: through a proxy, the proxy would choose
        the address.
    """

    def __init__(
        self,
        cache_dir: Path,
        *,
        timeout: float = 30.0,
        min_interval: float = 1.0,
        contact: str = "",
        retries: int = 1,
        backoff: float = 1.0,
        host_floors: dict[str, float] | None = None,
        search_floors: dict[str, tuple[tuple[str, ...], float]] | None = None,
        max_text_bytes: int = MAX_TEXT_BYTES,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._cache_dir = cache_dir
        self._timeout = timeout
        self._min_interval = min_interval
        self._retries = retries
        self._backoff = backoff
        self._floors = HOST_FLOORS if host_floors is None else host_floors
        self._search_floors = SEARCH_FLOORS if search_floors is None else search_floors
        self._clock = clock
        self._sleep = sleep
        self._max_text_bytes = max_text_bytes
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": user_agent(contact)},
            event_hooks={"request": [self._only_allowed_hosts]},
            follow_redirects=False,
            transport=transport or PublicOnlyTransport(),
        )
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._host_last: dict[str, float] = {}
        self._inflight: dict[str, asyncio.Future] = {}
        self._live_calls = 0
        self._cache_hits = 0
        self._shared_waits = 0
        self._hosts_called: dict[str, int] = {}
        self._last_error: dict | None = None

    # ------------------------------------------------------------------ #
    # Counters
    # ------------------------------------------------------------------ #
    @property
    def live_calls(self) -> int:
        """int: Requests sent this session, retries and downloads included."""
        return self._live_calls

    @property
    def cache_hits(self) -> int:
        """int: Answers served from the disk cache this session."""
        return self._cache_hits

    @property
    def shared_waits(self) -> int:
        """int: Calls answered by joining an identical request already in flight."""
        return self._shared_waits

    @property
    def hosts_called(self) -> dict[str, int]:
        """dict: Live requests this session, by host."""
        return dict(self._hosts_called)

    @property
    def last_error(self) -> dict | None:
        """dict or None: The most recent failure this session."""
        return self._last_error

    @property
    def cache_dir(self) -> Path:
        """Path: Where answers are cached."""
        return self._cache_dir

    def interval(self, host: str) -> float:
        """The least seconds between two requests to ``host``."""
        return max(self._min_interval, self._floors.get(host, 0.0))

    def search_interval(self, host: str) -> float:
        """The least seconds between two database searches on ``host``; 0 if none count."""
        return self._search_floors.get(host, ((), 0.0))[1]

    def _is_search(self, host: str, path: str) -> bool:
        prefixes = self._search_floors.get(host, ((), 0.0))[0]
        return any(path.startswith(prefix) for prefix in prefixes)

    # ------------------------------------------------------------------ #
    # Lifecycle and the host allowlist
    # ------------------------------------------------------------------ #
    async def aclose(self) -> None:
        """Close the HTTP transport."""
        await self._http.aclose()

    async def __aenter__(self) -> ArchiveHttp:
        """Return the client."""
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Close the transport."""
        await self.aclose()

    async def _only_allowed_hosts(self, request: httpx.Request) -> None:
        """Refuse any request that is not https to an allowed host."""
        host = request.url.host.lower()
        if request.url.scheme != "https" or host not in ALLOWED_HOSTS:
            raise HostNotAllowed(
                f"refusing a request to {host!r}: this server reaches only "
                f"{' and '.join(sorted(ALLOWED_HOSTS))}"
            )

    # ------------------------------------------------------------------ #
    # Requests
    # ------------------------------------------------------------------ #
    async def get_json(self, url: str, *, ttl_days: float, refresh: bool = False) -> Any:
        """GET a JSON answer; cached and shared while in flight.

        Raises
        ------
        SiteError
            For any failure. Nothing is cached.
        HostNotAllowed
            For a host off the allowlist, before anything is sent.
        """
        return await self._cached(
            "json", url, ttl_days, refresh, lambda: self._fetch(url, decode_json, "json")
        )

    async def get_text(
        self, url: str, *, ttl_days: float, refresh: bool = False, accept: str = "html"
    ) -> str:
        """GET an HTML page (or, with ``accept="xml"``, an XML file) as text; cached."""
        return await self._cached(
            "text", url, ttl_days, refresh, lambda: self._fetch(url, decode_text, accept)
        )

    async def get_location(self, url: str, *, ttl_days: float, refresh: bool = False) -> dict:
        """GET without following a redirect: ``{"status", "location"}`` or ``{"status", "text"}``.

        For a permalink service, whose answer *is* where it redirects. The
        location is returned as written, never requested by this call.
        """

        async def fetch() -> dict:
            self._check_host(url)
            response = await self._send(
                url, limit=self._max_text_bytes, follow=False, accept="html"
            )
            if response.status_code in (301, 302, 303, 307, 308):
                return {
                    "status": response.status_code,
                    "location": response.headers.get("location", ""),
                }
            return {"status": response.status_code, "text": decode_text(response)}

        return await self._cached("hop", url, ttl_days, refresh, fetch)

    async def fetch_image(self, url: str, *, max_bytes: int = MAX_IMAGE_BYTES) -> tuple[bytes, str]:
        """GET an image's bytes and their format, never cached.

        Raises
        ------
        SiteError
            If the site refuses, or sends something that is not an image
            (``not_an_image``), or more than ``max_bytes`` (``too_large``).
        """
        self._check_host(url)
        response = await self._send(
            url,
            limit=max_bytes,
            accept="image",
            timeout=httpx.Timeout(self._timeout, read=DOWNLOAD_TIMEOUT),
        )
        body = response.content
        kind = sniff_format(body[:16])
        if kind == "unknown":
            error = SiteError(
                "not_an_image",
                "the site answered with something that is not an image "
                f"({response.headers.get('content-type', 'no content type')}); nothing was saved",
                status=response.status_code,
                url=url,
            )
            self._note(error)
            raise error
        return body, kind

    def _check_host(self, url: str) -> None:
        """Refuse an off-list host before the cache or the network is consulted."""
        parts = urlsplit(url)
        if parts.scheme != "https" or (parts.hostname or "").lower() not in ALLOWED_HOSTS:
            raise HostNotAllowed(
                f"refusing a request to {parts.hostname!r}: this server reaches only "
                f"{' and '.join(sorted(ALLOWED_HOSTS))}"
            )

    async def _cached(
        self,
        kind: str,
        url: str,
        ttl_days: float,
        refresh: bool,
        make: Callable[[], Awaitable[Any]],
    ) -> Any:
        self._check_host(url)
        key = _key(kind, url)
        if not refresh:
            cached = self._cache_get(key, ttl_days * _DAY)
            if cached is not None:
                self._cache_hits += 1
                return cached
        data = await self._shared(key, make)
        self._cache_put(key, data)
        return data

    async def _fetch(self, url: str, decoder: Callable[[httpx.Response], Any], accept: str) -> Any:
        response = await self._send(url, limit=self._max_text_bytes, accept=accept)
        try:
            return decoder(response)
        except SiteError as exc:
            self._note(exc)
            raise

    async def _send(
        self, url: str, *, limit: int, follow: bool = True, accept: str = "json", **kwargs
    ) -> httpx.Response:
        """One GET, paced, retried and redirected by hand; the final response.

        Raises
        ------
        SiteError
            On a status of 400 or more, no response, a bot challenge, a
            redirect to another host, or a body over ``limit`` bytes.
        HostNotAllowed
            If a host is not allowed, or its name leads to an address that is
            not public. Never retried.
        """
        attempt = 0
        while True:
            try:
                response = await self._follow(
                    url, limit=limit, follow=follow, accept=accept, **kwargs
                )
            except SiteError as exc:
                error = exc
                response = None
            else:
                if response.status_code < 400:
                    return response
                error = _http_error(response, url)
            retryable = error.code in ("no_response", "rate_limited") or error.status >= 500
            if not retryable or attempt >= self._retries:
                self._note(error)
                raise error
            attempt += 1
            wait = _retry_after(response)
            if wait is None:
                wait = self._backoff * 2 ** (attempt - 1) + random.uniform(0, self._backoff / 2)
            wait = min(wait, RETRY_AFTER_CAP)
            logger.info("%s -> %s; retry %d in %.1fs", url, error.code, attempt, wait)
            await self._sleep(wait)

    async def _follow(
        self, url: str, *, limit: int, follow: bool, accept: str, **kwargs
    ) -> httpx.Response:
        """Send, following redirects only within the same host, and only when asked."""
        for _ in range(MAX_REDIRECTS + 1):
            response = await self._paced(url, limit=limit, accept=accept, **kwargs)
            if not follow or response.status_code not in (301, 302, 303, 307, 308):
                return response
            location = urljoin(url, response.headers.get("location", ""))
            here = (urlsplit(url).hostname or "").lower()
            target = urlsplit(location)
            if target.scheme != "https" or (target.hostname or "").lower() != here:
                raise SiteError(
                    "redirected",
                    f"the site redirects this request to {location}",
                    status=response.status_code,
                    url=url,
                    location=location,
                )
            url = location
        raise SiteError("redirected", "too many redirects", url=url)

    async def _paced(self, url: str, *, limit: int, accept: str, **kwargs) -> httpx.Response:
        """Send one request once this host's turn and interval have come.

        The body is streamed and refused as soon as it passes ``limit``
        bytes, decoded, so neither a declared nor an undeclared size can make
        the client read more.
        """
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        search = self._is_search(host, parts.path)
        lock = self._host_locks.setdefault(host, asyncio.Lock())
        headers = {"Accept": _ACCEPT[accept]}
        async with lock:
            waits = []
            last = self._host_last.get(host)
            if last is not None:
                waits.append(self.interval(host) - (self._clock() - last))
            last_search = self._host_last.get(f"{host}#search")
            if search and last_search is not None:
                waits.append(self.search_interval(host) - (self._clock() - last_search))
            wait = max(waits, default=0.0)
            if wait > 0:
                await self._sleep(wait)
            self._host_last[host] = self._clock()
            if search:
                self._host_last[f"{host}#search"] = self._clock()
            self._live_calls += 1
            self._hosts_called[host] = self._hosts_called.get(host, 0) + 1
            try:
                async with self._http.stream("GET", url, headers=headers, **kwargs) as response:
                    body = await _read_capped(response, limit, url)
                return _with_body(response, body)
            except httpx.TimeoutException as exc:
                raise SiteError("timeout", _transport_text(exc), url=url) from None
            except httpx.TransportError as exc:
                raise SiteError("no_response", _transport_text(exc), url=url) from None

    # ------------------------------------------------------------------ #
    # Shared machinery
    # ------------------------------------------------------------------ #
    async def _shared(self, key: str, make: Callable[[], Awaitable[Any]]) -> Any:
        """Run ``make`` once for concurrent callers asking the same thing."""
        if (pending := self._inflight.get(key)) is not None:
            self._shared_waits += 1
            return await asyncio.shield(pending)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            data = await make()
        except asyncio.CancelledError:
            future.cancel()
            raise
        except Exception as exc:
            future.set_exception(exc)
            # Mark it retrieved: a failure nobody else was waiting on must
            # not be logged as "exception was never retrieved".
            future.exception()
            raise
        else:
            future.set_result(data)
            return data
        finally:
            self._inflight.pop(key, None)

    def _note(self, error: SiteError) -> None:
        self._last_error = {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "error": error.code,
            "status": error.status or None,
            "detail": error.detail[:300],
            "request": error.url[:300],
        }

    # ------------------------------------------------------------------ #
    # Cache
    # ------------------------------------------------------------------ #
    def _cache_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"

    def _cache_get(self, key: str, ttl: float) -> Any:
        """Return a cached answer, or None if absent, expired or unreadable."""
        path = self._cache_path(key)
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError, ValueError):
            # A truncated or hand-edited entry is a re-fetch, not a crash.
            logger.warning("discarding unreadable cache entry %s", path.name)
            return None
        if not isinstance(entry, dict) or "data" not in entry:
            return None
        stored = entry.get("stored")
        if not isinstance(stored, int | float) or time.time() - stored > ttl:
            return None
        return entry["data"]

    def _cache_put(self, key: str, data: Any) -> None:
        try:
            _write_atomically(
                self._cache_path(key), json.dumps({"stored": time.time(), "data": data})
            )
        except OSError:
            # A cache that cannot be written costs speed, not correctness.
            logger.warning("could not write the response cache in %s", self._cache_dir)


#: Accept headers by what a request expects back.
_ACCEPT = {
    "json": "application/json",
    "html": "text/html,application/xhtml+xml",
    "xml": "application/xml,text/xml",
    "image": "image/jpeg,image/*;q=0.8",
}


def write_new_image(target: Path, body: bytes, kind: str) -> int:
    """Write image bytes to a file that must not exist yet; the bytes written.

    Nothing is written unless ``target``'s suffix names ``kind``: a page scan
    saved as ``.jpg`` must be a JPEG. The file is created exclusively, so an
    existing one is never overwritten, and removed again if writing fails, so
    a partial file never passes for a finished one.

    Raises
    ------
    SiteError
        ``extension_mismatch`` if the suffix does not fit the format.
    FileExistsError
        If ``target`` exists. It is left untouched.
    """
    if target.suffix.lower() not in IMAGE_SUFFIXES.get(kind, ()):
        raise SiteError(
            "extension_mismatch",
            f"the site sent a {kind.upper()} image, which cannot be saved as "
            f"{target.name}; nothing was saved",
        )
    out = target.open("xb")
    try:
        with out:
            out.write(body)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return len(body)


def looks_like_challenge(text: str) -> bool:
    """Whether an HTML answer is a bot-check page rather than the page asked for."""
    head = text[:4000].lower()
    return "<html" in head and any(mark in head for mark in _CHALLENGE_MARKS)


def decode_json(response: httpx.Response) -> Any:
    """Decode a 2xx JSON answer, naming a web page or a bot check for what it is."""
    url = str(response.url)
    text = response.text
    try:
        return response.json()
    except ValueError:
        if looks_like_challenge(text):
            raise SiteError(
                "challenge",
                "the site answered with a bot check; it must be opened in a browser",
                status=response.status_code,
                url=url,
            ) from None
        raise SiteError(
            "not_json",
            "the site answered with something that is not JSON"
            + (" (a web page)" if text.lstrip()[:1] == "<" else ""),
            status=response.status_code,
            url=url,
        ) from None


def decode_text(response: httpx.Response) -> str:
    """A 2xx HTML answer as text, refusing a bot-check page."""
    text = response.text
    if looks_like_challenge(text):
        raise SiteError(
            "challenge",
            "the site answered with a bot check; it must be opened in a browser",
            status=response.status_code,
            url=str(response.url),
        )
    return text


async def _read_capped(response: httpx.Response, limit: int, url: str) -> bytes:
    """Read a streamed body, refusing it once it passes ``limit`` bytes."""
    too_large = SiteError(
        "too_large",
        f"the answer is over {limit / 1_000_000:g} MB, more than this server reads",
        status=response.status_code,
        url=url,
    )
    declared = response.headers.get("content-length", "").strip()
    if declared.isdigit() and int(declared) > limit:
        raise too_large
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > limit:
            raise too_large
        chunks.append(chunk)
    return b"".join(chunks)


def _with_body(response: httpx.Response, body: bytes) -> httpx.Response:
    """A complete response carrying ``body``, already decoded, in place of the stream."""
    spent = {"content-encoding", "content-length", "transfer-encoding"}
    return httpx.Response(
        response.status_code,
        headers=[(k, v) for k, v in response.headers.multi_items() if k.lower() not in spent],
        content=body,
        request=response.request,
        extensions=response.extensions,
    )


def _http_error(response: httpx.Response, url: str) -> SiteError:
    """Classify a 4xx or 5xx answer."""
    status = response.status_code
    text = response.text.strip()
    if response.headers.get("cf-mitigated", "").lower() == "challenge" or looks_like_challenge(
        text
    ):
        return SiteError(
            "challenge",
            "the site answered with a bot check; it must be opened in a browser",
            status=status,
            url=url,
        )
    if status == 429:
        return SiteError(
            "rate_limited", "the site asked for fewer requests", status=status, url=url
        )
    if text[:1] == "<":
        detail = response.reason_phrase or "an HTML error page"
    else:
        detail = " ".join(text.split())[:300] or response.reason_phrase
    return SiteError("http_error", detail, status=status, url=url)


def _transport_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}".rstrip(": ")


def _retry_after(response: httpx.Response | None) -> float | None:
    """Seconds a ``Retry-After`` header asks for, or None if absent or unreadable."""
    if response is None:
        return None
    raw = (response.headers.get("retry-after") or "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def _key(kind: str, url: str) -> str:
    return hashlib.sha256(f"{kind} {url}".encode()).hexdigest()[:24]


def _write_atomically(path: Path, text: str) -> None:
    """Write a file so a reader never sees it half-written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
