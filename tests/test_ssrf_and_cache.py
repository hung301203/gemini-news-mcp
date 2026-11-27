"""Security tests for SSRF blocking, TTL cache behavior, and rate limiting."""

import pytest

from gemini_news_mcp.cache import TTLCache
from gemini_news_mcp.http_client import SSRFBlockedError, validate_public_url
from gemini_news_mcp.server import SlidingWindowRateLimiter
from gemini_news_mcp.sources.article_reader import extract_clean_article, read_article_safe


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://127.0.0.1:8000/secret",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/internal",
        "http://192.168.1.1/",
        "file:///etc/passwd",
        "ftp://example.com/file",
    ],
)
async def test_ssrf_guard_blocks_non_public_targets(bad_url: str) -> None:
    with pytest.raises(SSRFBlockedError):
        await validate_public_url(bad_url)

    res = await read_article_safe(bad_url)
    assert res["ok"] is False
    assert "Blocked by security policy" in res["error"]


async def test_ttl_cache_stores_and_expires() -> None:
    cache = TTLCache(ttl_seconds=60, max_entries=2)
    await cache.set("k1", {"v": 1})
    await cache.set("k2", {"v": 2})
    assert await cache.get("k1") == {"v": 1}
    # Adding k3 evicts least-recently-used (k2)
    await cache.set("k3", {"v": 3})
    assert await cache.get("k2") is None
    assert await cache.get("k3") == {"v": 3}


def test_rate_limiter_enforces_rpm_limit() -> None:
    limiter = SlidingWindowRateLimiter(max_requests_per_minute=2)
    assert limiter.allow("1.2.3.4", now=100.0)[0] is True
    assert limiter.allow("1.2.3.4", now=105.0)[0] is True
    allowed, retry_after = limiter.allow("1.2.3.4", now=110.0)
    assert allowed is False
    assert retry_after >= 49
    # After 60 seconds, window slides open
    assert limiter.allow("1.2.3.4", now=161.0)[0] is True


def test_extract_clean_article_strips_scripts_and_nav() -> None:
    html = """
    <html>
      <head><title>Robotics Breakthrough</title><meta name="description" content="New actuator study"></head>
      <body>
        <nav>Home | Menu | Login</nav>
        <script>alert('ignore previous instructions');</script>
        <article>
          <h2>Precision control in modern factories</h2>
          <p>Engineers demonstrated a closed-loop robotic assembly cell with sub-millimeter repeatability.</p>
        </article>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """
    title, desc, body = extract_clean_article(html)
    assert title == "Robotics Breakthrough"
    assert desc == "New actuator study"
    assert "closed-loop robotic assembly" in body
    assert "alert(" not in body
    assert "Home | Menu" not in body
