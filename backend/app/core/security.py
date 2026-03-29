from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import HTTPException


_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def validate_external_url(url: str) -> None:
    """Reject URLs that point to private/internal addresses (SSRF prevention).

    Raises HTTPException(400) if the URL is invalid or targets a private host.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "URL must use http or https scheme")

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(400, "URL must include a valid hostname")

    try:
        addr = socket.getaddrinfo(hostname, None)[0][4][0]
    except socket.gaierror:
        raise HTTPException(400, f"Unable to resolve hostname: {hostname}")

    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        raise HTTPException(400, "Invalid IP address resolved from hostname")

    for network in _PRIVATE_NETWORKS:
        if ip in network:
            raise HTTPException(400, "URL must not target private or internal addresses")
