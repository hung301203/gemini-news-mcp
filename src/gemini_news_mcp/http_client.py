"""Shared async HTTP client with SSRF protection, timeouts, and bounded reads."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

USER_AGENT = (
    "Mozilla/5.0 (compatible; GeminiNewsMCP/0.1; +https://github.com/gemini-news-mcp)"
)


class SSRFBlockedError(ValueError):
    """Raised when a URL resolves to a disallowed scheme or non-public IP."""


def _is_public_ip(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return ip.is_global and not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def validate_public_url(url: str) -> str:
    """Validate scheme and confirm all resolved DNS targets are public IPs."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise SSRFBlockedError(f"Unsupported URL scheme: {parsed.scheme!r}")
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise SSRFBlockedError("URL has no hostname")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise SSRFBlockedError(f"Blocked local hostname: {hostname}")

    # Direct IP literal check
    try:
        if not _is_public_ip(hostname):
            raise SSRFBlockedError(f"Blocked non-public IP: {hostname}")
        return url.strip()
    except ValueError:
        pass

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFBlockedError(f"Could not resolve hostname {hostname}: {exc}") from exc

    if not infos:
        raise SSRFBlockedError(f"No DNS records for hostname: {hostname}")

    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        if not _is_public_ip(ip_str):
            raise SSRFBlockedError(f"Hostname {hostname} resolved to non-public IP {ip_str}")

    return url.strip()


async def fetch_text(
    url: str,
    *,
    timeout: float = 7.0,
    max_bytes: int = 1_500_000,
    check_ssrf: bool = False,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Fetch response text and final URL with bounded download size."""
    req_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        req_headers.update(headers)

    current_url = url
    max_redirects = 5
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        follow_redirects=not check_ssrf,
        headers=req_headers,
    ) as client:
        for _ in range(max_redirects + 1):
            if check_ssrf:
                current_url = await validate_public_url(current_url)

            async with client.stream("GET", current_url, params=params) as resp:
                if check_ssrf and resp.status_code in {301, 302, 303, 307, 308}:
                    location = resp.headers.get("location")
                    if not location:
                        break
                    current_url = urljoin(str(resp.url), location)
                    params = None
                    continue

                resp.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        chunks.append(chunk[: max_bytes - (total - len(chunk))])
                        break
                    chunks.append(chunk)
                raw = b"".join(chunks)
                encoding = resp.encoding or "utf-8"
                return raw.decode(encoding, errors="replace"), str(resp.url)

    raise httpx.TooManyRedirects(f"Too many redirects fetching {url}")


async def fetch_json(
    url: str,
    *,
    timeout: float = 7.0,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    """Fetch JSON payload from a trusted upstream API."""
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        follow_redirects=True,
        headers=req_headers,
    ) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
