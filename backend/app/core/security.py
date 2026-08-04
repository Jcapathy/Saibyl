from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import HTTPException

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _unwrap(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> list:
    """Every address this one is, not just the one it is written as.

    `::ffff:127.0.0.1` is loopback wearing a v6 hat: it matches none of the v6
    private networks and none of the v4 ones either, because it is not an
    `IPv4Address`. The same holds for 6to4 and Teredo, which carry a v4 address
    in their payload. Each embedded address is checked on its own terms.
    """
    candidates = [ip]
    for attr in ("ipv4_mapped", "sixtofour"):
        embedded = getattr(ip, attr, None)
        if embedded is not None:
            candidates.append(embedded)

    teredo = getattr(ip, "teredo", None)
    if teredo is not None:
        candidates.extend(teredo)  # (server, client)

    return candidates


def _reject_if_internal(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    for candidate in _unwrap(ip):
        if any(candidate in network for network in _PRIVATE_NETWORKS):
            raise HTTPException(400, "URL must not target private or internal addresses")
        # Backstop for everything the explicit list does not enumerate:
        # loopback, link-local, multicast, and the reserved ranges.
        if not candidate.is_global:
            raise HTTPException(400, "URL must not target private or internal addresses")


def validate_external_url(url: str) -> None:
    """Reject URLs that point to private/internal addresses (SSRF prevention).

    Every address the hostname resolves to is checked, not just the first.
    `getaddrinfo` orders its results by the system's address-selection policy,
    so a host that resolves to a public address and a loopback one could put
    either first — checking `[0]` alone means the check passes or fails by
    resolver ordering.

    Raises HTTPException(400) if the URL is invalid or targets a private host.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "URL must use http or https scheme")

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(400, "URL must include a valid hostname")

    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise HTTPException(400, f"Unable to resolve hostname: {hostname}")

    if not infos:
        raise HTTPException(400, f"Unable to resolve hostname: {hostname}")

    for info in infos:
        # Strip any IPv6 scope id ("fe80::1%eth0"), which ip_address rejects.
        addr = str(info[4][0]).split("%")[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            raise HTTPException(400, "Invalid IP address resolved from hostname")

        _reject_if_internal(ip)
