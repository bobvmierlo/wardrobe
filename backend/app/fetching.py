"""Fetching a URL somebody else typed.

Two features hand the server a URL and ask it to go and get it: adding a garment
from a photo URL, and reading the details off a webshop page. Both are useful and
both are, without care, a way to make the server knock on doors only it can
reach — the admin panel of another container, a router's web interface, a cloud
metadata endpoint. The app runs on a home server, usually on the same network as
everything else that home server runs, so "only the server can reach it" is
exactly the problem: *any* signed-in user, a kijker on a shared kast included,
would be borrowing that reach.

So a remote fetch goes through here, and here it is deliberately dull:

* only ``http`` and ``https``;
* the hostname is resolved first, and refused if **any** of its addresses is
  private, loopback, link-local or otherwise not a public internet address;
* redirects are followed by hand, at most :data:`MAX_REDIRECTS` of them, with
  the same check applied at every hop — a redirect to ``127.0.0.1`` is the
  obvious way around a check that only looks at what was typed;
* the body is read through a cap, so a URL that streams forever cannot fill
  the disk or the memory.

What this does **not** close is the gap between resolving a name and connecting
to it: a DNS server that answers differently the second time can still slip an
address past the check. Closing it properly means pinning the connection to the
address that was checked, which breaks TLS verification unless carefully
reassembled. Checking every address of every hop makes the window small, and a
home server behind a reverse proxy is not worth that complexity — but the gap is
real, so it is written down rather than implied. Operators who genuinely want
their own network reachable can set ``WARDROBE_FETCH_ALLOW_PRIVATE=true``.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from .config import settings
from .logging_setup import get_logger

log = get_logger("fetching")

#: Enough for the redirect chains shops really use (http → https → www → page).
MAX_REDIRECTS = 4

DEFAULT_TIMEOUT = 15.0


def _client(timeout: float) -> httpx.Client:
    """The HTTP client a remote fetch uses.

    Redirects are never followed automatically: each hop has to pass the same
    address check, and httpx following them for us would be exactly the hole
    this module exists to close. A function so the tests can put a fake
    webshop behind it.
    """
    return httpx.Client(timeout=timeout, follow_redirects=False)


class FetchRefused(Exception):
    """The app would not even try: bad scheme, or an address it must not visit.

    Kept apart from :class:`FetchFailed` because the two deserve different
    answers. This one is a refusal by policy and says so; the other is the wider
    internet being the wider internet.
    """


class FetchFailed(Exception):
    """The attempt was made and did not work: no route, a timeout, a 404, a 403."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        #: The status the remote side answered with, when it answered at all.
        self.status = status


@dataclass
class Fetched:
    body: bytes
    #: Where the bytes actually came from, after any redirects.
    url: str
    content_type: str
    encoding: str | None


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Whether this address belongs to the public internet.

    An IPv4-mapped IPv6 address is unwrapped first: "::ffff:127.0.0.1" is
    loopback, and asking the IPv6 object directly would not say so.
    """
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _check_target(url: str) -> None:
    """Refuse a URL the server has no business fetching."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchRefused("Alleen http- en https-adressen kunnen worden opgehaald")
    host = parsed.hostname
    if not host:
        raise FetchRefused("Dit adres heeft geen servernaam")
    if settings.fetch_allow_private:
        return

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        resolved = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FetchFailed(f"De servernaam '{host}' kon niet worden opgezocht") from exc

    addresses = {info[4][0] for info in resolved}
    if not addresses:
        raise FetchFailed(f"De servernaam '{host}' leverde geen adres op")

    for address in addresses:
        try:
            ip = ipaddress.ip_address(address.split("%")[0])  # strip any zone id
        except ValueError:
            raise FetchRefused("Dit adres kon niet worden gecontroleerd") from None
        if not _is_public(ip):
            # Said out loud: someone aiming at their own network deserves to
            # know it was refused on purpose, not that "the site was down".
            log.warning(
                "Geweigerd om %s op te halen: %s is geen publiek internetadres",
                host,
                address,
            )
            raise FetchRefused(
                "Dit adres wijst naar een apparaat in je eigen netwerk."
                " De app haalt alleen adressen van het open internet op."
            )


def fetch_remote(
    url: str,
    *,
    limit: int,
    timeout: float = DEFAULT_TIMEOUT,
    headers: dict[str, str] | None = None,
) -> Fetched:
    """Fetch ``url`` with the checks above. ``limit`` caps the body in bytes.

    A body that runs past the cap is an error rather than a truncation: half an
    image and half a web page are both useless, and silently returning either
    would turn a size problem into a puzzling parse failure later on.
    """
    current = url
    try:
        with _client(timeout) as client:
            for _hop in range(MAX_REDIRECTS + 1):
                _check_target(current)
                with client.stream("GET", current, headers=headers or {}) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchFailed("De server stuurde een omleiding zonder adres")
                        current = urljoin(current, location)
                        continue
                    if response.status_code >= 400:
                        raise FetchFailed(
                            f"De server antwoordde met foutcode {response.status_code}",
                            status=response.status_code,
                        )
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > limit:
                            raise FetchFailed("Het bestand op dit adres is te groot")
                        chunks.append(chunk)
                    return Fetched(
                        body=b"".join(chunks),
                        url=str(response.url),
                        content_type=response.headers.get("content-type", ""),
                        encoding=response.charset_encoding,
                    )
    except (FetchRefused, FetchFailed):
        raise
    except httpx.HTTPError as exc:
        raise FetchFailed(f"Het adres kon niet worden opgehaald: {exc.__class__.__name__}") from exc

    raise FetchFailed("Te veel omleidingen achter elkaar")
