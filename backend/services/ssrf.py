"""SSRF defence for server-side URL fetching (update.md §5.4).

Only http/https URLs are allowed. Literal private/loopback/link-local/
reserved/multicast IPs are rejected, and hostnames are resolved and every
resulting IP is checked. This runs *before* Firecrawl/httpx fetching;
Firecrawl is a fetcher, not a security boundary.
"""
import ipaddress
import socket
from urllib.parse import urlparse


def _ip_is_blocked(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_public_url(url: str, *, resolve: bool = True) -> str:
    """Raise ValueError if url is not a safe public http(s) URL."""
    if not url or len(url) > 2048:
        raise ValueError("URL missing or too long")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Blocked URL scheme: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise ValueError("URL has no hostname")
    if host.lower() in ("localhost",) or host.endswith(".local") or host.endswith(".internal"):
        raise ValueError(f"Blocked internal hostname: {host}")
    # Literal IP?
    try:
        ipaddress.ip_address(host)
        literal = True
    except ValueError:
        literal = False
    if literal:
        if _ip_is_blocked(host):
            raise ValueError(f"Blocked non-public IP: {host}")
        return url
    if resolve:
        try:
            infos = socket.getaddrinfo(host, None)
        except OSError as exc:
            raise ValueError(f"Cannot resolve hostname: {host}") from exc
        for info in infos:
            ip_str = info[4][0]
            if not isinstance(ip_str, str):
                raise ValueError(f"Cannot validate DNS result for hostname: {host}")
            if _ip_is_blocked(ip_str):
                raise ValueError(f"Hostname resolves to non-public IP: {host} -> {ip_str}")
    return url
