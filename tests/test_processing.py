"""Unit tests for deduplication, cross-source corroboration, driver tagging, and sanitization."""

from datetime import datetime, timezone

from gemini_news_mcp.models import NewsItem
from gemini_news_mcp.processing import (
    dedupe_and_corroborate,
    normalize_url,
    rank_and_filter,
    sanitize_text,
    tag_finance_drivers,
)

NOW = datetime(2026, 11, 27, 15, 0, tzinfo=timezone.utc)


def test_normalize_url_strips_tracking_params() -> None:
    u1 = "https://www.reuters.com/markets/gold-surge/?utm_source=x&fbclid=123#top"
    u2 = "https://www.reuters.com/markets/gold-surge"
    assert normalize_url(u1) == normalize_url(u2)


def test_sanitize_text_strips_html_and_control_chars() -> None:
    raw = "<b>Gold</b> jumps &amp; Fed\x00 signals\n\n  pause"
    assert sanitize_text(raw) == "Gold jumps & Fed signals pause"


def test_dedupe_merges_same_story_across_sources_and_keeps_higher_authority() -> None:
    items = [
        NewsItem(
            title="Gold prices jump to record high after Federal Reserve hints at rate cut",
            url="https://unknown-blog.example.com/gold-record",
            source_name="Finance Blog",
            source_domain="unknown-blog.example.com",
            domain="finance",
            published_at="2026-11-27T11:00:00+00:00",
        ),
        NewsItem(
            title="Gold prices jump to record high after Federal Reserve hints rate cut",
            url="https://reuters.com/markets/gold-record-high",
            source_name="Reuters",
            source_domain="reuters.com",
            domain="finance",
            published_at="2026-11-27T10:30:00+00:00",
        ),
    ]
    clustered = dedupe_and_corroborate(items, now=NOW)
    assert len(clustered) == 1
    assert clustered[0].source_domain == "reuters.com"
    assert "Finance Blog" in clustered[0].corroborated_by
    assert "interest_rates_central_bank" in clustered[0].driver_tags
    assert "commodities_fx" in clustered[0].driver_tags


def test_rank_and_filter_drops_old_and_low_credibility_items() -> None:
    items = [
        NewsItem(
            title="Autonomous industrial robot arm sets precision record in semiconductor plant",
            url="https://spectrum.ieee.org/robot-arm-record",
            source_name="IEEE Spectrum",
            source_domain="spectrum.ieee.org",
            domain="automation",
            published_at="2026-11-27T09:00:00+00:00",
        ),
        NewsItem(
            title="Old automation article from last month",
            url="https://spectrum.ieee.org/old-article",
            source_name="IEEE Spectrum",
            source_domain="spectrum.ieee.org",
            domain="automation",
            published_at="2026-10-01T09:00:00+00:00",
        ),
        NewsItem(
            title="Miracle cure instant detox secret doctors hate",
            url="https://spam.example.com/detox",
            source_name="Spam Site",
            source_domain="spam.example.com",
            domain="wellness",
            published_at="2026-11-27T12:00:00+00:00",
        ),
    ]
    ranked, filtered = rank_and_filter(items, max_age_hours=72, min_credibility=45, limit=10, now=NOW)
    assert len(ranked) == 1
    assert ranked[0].source_domain == "spectrum.ieee.org"
    assert filtered == 1


def test_tag_finance_drivers_vietnamese() -> None:
    tags = tag_finance_drivers("VN-Index giảm mạnh do áp lực tỷ giá USD và khối ngoại bán ròng")
    assert "commodities_fx" in tags
    assert "flows_sentiment" in tags
