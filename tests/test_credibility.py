"""Unit tests for the transparent 0-100 credibility scoring engine."""

from datetime import datetime, timezone

from gemini_news_mcp.credibility import evaluate_domain, score_item
from gemini_news_mcp.models import NewsItem


NOW = datetime(2026, 11, 27, 15, 0, tzinfo=timezone.utc)


def test_pubmed_clinical_trial_earns_tier_a() -> None:
    item = NewsItem(
        title="Randomized clinical trial of evening light restriction on sleep quality",
        url="https://pubmed.ncbi.nlm.nih.gov/39999999/",
        source_name="PubMed — Sleep Medicine",
        source_domain="pubmed.ncbi.nlm.nih.gov",
        domain="wellness",
        language="en",
        published_at="2026-11-26T10:00:00+00:00",
        summary="A randomized clinical trial evaluating circadian sleep improvements.",
        authors=["Nguyen A", "Smith B"],
        evidence_ids=["PMID:39999999"],
    )
    scored = score_item(item, now=NOW)
    assert scored.credibility_score >= 80
    assert scored.credibility_tier == "A"
    assert any("PMID:39999999" in n for n in scored.credibility_notes)


def test_wellness_clickbait_is_heavily_penalized() -> None:
    item = NewsItem(
        title="Thần dược uống thứ này mỗi sáng chữa dứt điểm mất ngủ",
        url="https://random-blog.example.com/than-duoc",
        source_name="Random Health Blog",
        source_domain="random-blog.example.com",
        domain="wellness",
        language="vi",
        published_at="2026-11-27T08:00:00+00:00",
        summary="Bí quyết 1 đêm giảm cân thần tốc, nội dung tài trợ.",
    )
    scored = score_item(item, now=NOW)
    assert scored.credibility_tier == "Low"
    assert scored.credibility_score < 20
    assert any("Cảnh báo" in n for n in scored.credibility_notes)


def test_finance_corroboration_boosts_score_across_sources() -> None:
    single = NewsItem(
        title="Federal Reserve signals pause on interest rate cuts after CPI report",
        url="https://www.cnbc.com/2026/11/27/fed-cpi.html",
        source_name="CNBC",
        source_domain="cnbc.com",
        domain="finance",
        published_at="2026-11-27T12:00:00+00:00",
        summary="Treasury yields rose after inflation beat expectations.",
    )
    corroborated = NewsItem(
        title=single.title,
        url=single.url,
        source_name=single.source_name,
        source_domain=single.source_domain,
        domain="finance",
        published_at=single.published_at,
        summary=single.summary,
        corroborated_by=["Reuters", "MarketWatch"],
    )
    s1 = score_item(single, now=NOW).credibility_score
    s2 = score_item(corroborated, now=NOW).credibility_score
    assert s2 - s1 == 25
    assert corroborated.credibility_tier == "A"


def test_finance_rumor_penalty() -> None:
    item = NewsItem(
        title="Tin đồn cổ phiếu ABC sắp x10 tài khoản, phím hàng mua ngay kẻo lỡ",
        url="https://unknown-stock-tips.example.net/abc",
        source_name="Stock Tips",
        source_domain="unknown-stock-tips.example.net",
        domain="finance",
        language="vi",
        published_at="2026-11-27T10:00:00+00:00",
    )
    scored = score_item(item, now=NOW)
    assert scored.credibility_tier == "Low"
    assert scored.credibility_score < 20


def test_evaluate_domain_known_vs_unknown() -> None:
    known = evaluate_domain("https://spectrum.ieee.org/humanoid-robot-factory")
    unknown = evaluate_domain("https://my-unknown-site.example.org/post")
    assert known["whitelisted"] is True
    assert known["estimated_tier"] == "A"
    assert unknown["whitelisted"] is False
    assert unknown["estimated_tier"] == "Low"
