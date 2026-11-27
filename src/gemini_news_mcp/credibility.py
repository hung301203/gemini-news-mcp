"""Transparent, deterministic credibility scoring (0-100, Tier A/B/C/Low)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from gemini_news_mcp.config import DOMAIN_AUTHORITY, PUBLISHER_ALIASES
from gemini_news_mcp.models import NewsItem

# Clickbait, pseudoscience, sponsored PR, and unverified rumor patterns (VI + EN)
WELLNESS_PENALTY_PATTERNS: list[tuple[re.Pattern[str], int, str]] = [
    (
        re.compile(
            r"\b(miracle cure|cure[sd]? cancer|secret doctors hate|instant detox|melt belly fat|"
            r"thần dược|chữa dứt điểm|chữa bách bệnh|bí quyết 1 đêm|giảm cân thần tốc|uống thứ này mỗi sáng)\b",
            re.IGNORECASE,
        ),
        25,
        "Dấu hiệu giật gân / thiếu căn cứ y khoa",
    ),
    (
        re.compile(
            r"\b(one weird trick|shocking truth|you won't believe|sponsored|advertorial|quảng cáo|tài trợ)\b",
            re.IGNORECASE,
        ),
        18,
        "Dấu hiệu clickbait hoặc nội dung tài trợ",
    ),
]

FINANCE_PENALTY_PATTERNS: list[tuple[re.Pattern[str], int, str]] = [
    (
        re.compile(
            r"\b(100x|10x guaranteed|get rich quick|sure thing stock|phím hàng|lãi khủng chắc chắn|"
            r"x10 tài khoản|mua ngay kẻo lỡ|siêu cổ phiếu bí mật)\b",
            re.IGNORECASE,
        ),
        25,
        "Dấu hiệu lùa gà / cam kết lợi nhuận bất thường",
    ),
    (
        re.compile(
            r"\b(unconfirmed rumor|rumored to|rumour|tin đồn|nghe đồn|chưa kiểm chứng|sponsored|pr)\b",
            re.IGNORECASE,
        ),
        12,
        "Nội dung tin đồn hoặc chưa xác thực chính thức",
    ),
]

EVIDENCE_POSITIVE_PATTERN = re.compile(
    r"\b(randomized|clinical trial|meta-analysis|cohort study|peer-reviewed|published in|"
    r"journal|university|institute|federal reserve|fomc|cpi|gdp|earnings|sec filing|"
    r"nghiên cứu lâm sàng|đại học|tạp chí khoa học|báo cáo tài chính|ngân hàng nhà nước|cục dự trữ liên bang|lạm phát)\b",
    re.IGNORECASE,
)


def extract_domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def lookup_domain_authority(domain: str, source_name: str = "") -> tuple[int, str, str, bool]:
    """Return (score_out_of_45, source_type, canonical_label, is_verified_whitelist)."""
    d = domain.lower().strip()
    if d.startswith("www."):
        d = d[4:]

    # Exact match first
    if d in DOMAIN_AUTHORITY:
        score, stype, label = DOMAIN_AUTHORITY[d]
        return score, stype, label, True

    # Suffix match (e.g. sub.reuters.com -> reuters.com)
    for known_host, (score, stype, label) in DOMAIN_AUTHORITY.items():
        if d.endswith("." + known_host):
            return score, stype, label, True

    # Publisher name alias fallback (especially useful for Google News RSS items)
    norm_source = source_name.lower().strip()
    for alias, mapped_host in PUBLISHER_ALIASES.items():
        if alias in norm_source:
            score, stype, label = DOMAIN_AUTHORITY[mapped_host]
            return score, stype, label, True

    if d and d not in {"news.google.com", ""}:
        return 14, "unverified", source_name or d, False
    return 12, "unverified", source_name or "Unknown", False


def tier_from_score(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "Low"


def evaluate_domain(url_or_domain: str) -> dict[str, object]:
    """Quick credibility profile for a single URL or domain (used by read_article)."""
    domain = extract_domain(url_or_domain) if "://" in url_or_domain else url_or_domain.lower().strip()
    auth_score, stype, label, verified = lookup_domain_authority(domain)
    # Normalize authority-only baseline to 0-100 scale for single-article context
    approx_score = min(90, int(auth_score * 1.9)) if verified else 35
    return {
        "domain": domain,
        "publisher": label,
        "source_type": stype,
        "whitelisted": verified,
        "domain_authority": auth_score,
        "estimated_tier": tier_from_score(approx_score),
    }


def score_item(item: NewsItem, now: datetime | None = None) -> NewsItem:
    """Compute and attach transparent 0-100 credibility score, tier, and reasons."""
    now = now or datetime.now(timezone.utc)
    notes: list[str] = []

    # 1. Source authority (max 50)
    auth_score, source_type, canonical_label, is_verified = lookup_domain_authority(
        item.source_domain, item.source_name
    )
    if is_verified:
        notes.append(f"Nguồn uy tín ({canonical_label}, {source_type}: +{auth_score})")
    else:
        notes.append(f"Domain chưa nằm trong whitelist ({item.source_domain or 'unknown'}: +{auth_score})")

    # 2. Cross-source corroboration (max 25)
    corr_count = len(item.corroborated_by)
    if corr_count >= 2:
        corr_score = 25
        notes.append(f"Xác nhận chéo bởi {corr_count + 1} nguồn độc lập (+25)")
    elif corr_count == 1:
        corr_score = 14
        notes.append("Xác nhận chéo bởi 2 nguồn độc lập (+14)")
    else:
        corr_score = 0

    # 3. Evidence signals (+25 max) & domain-specific penalties (-30 max)
    evidence_score = 0
    if item.evidence_ids:
        evidence_score += 22
        notes.append(f"Có mã định danh nghiên cứu ({', '.join(item.evidence_ids[:2])}: +22)")
    elif source_type in {"academic", "official", "medical_institution", "market_data"}:
        evidence_score += 15
        notes.append("Nguồn sơ cấp / tổ chức chuyên môn (+15)")

    combined_text = f"{item.title} {item.summary}"
    if EVIDENCE_POSITIVE_PATTERN.search(combined_text):
        bonus = min(25 - evidence_score, 8)
        if bonus > 0:
            evidence_score += bonus
            notes.append(f"Có trích dẫn số liệu/nghiên cứu cụ thể (+{bonus})")

    penalty = 0
    patterns = (
        WELLNESS_PENALTY_PATTERNS
        if item.domain == "wellness"
        else FINANCE_PENALTY_PATTERNS
        if item.domain == "finance"
        else WELLNESS_PENALTY_PATTERNS[:1] + FINANCE_PENALTY_PATTERNS[:1]
    )
    for pat, pts, reason in patterns:
        if pat.search(combined_text):
            penalty = min(30, penalty + pts)
            notes.append(f"Cảnh báo: {reason} (-{pts})")

    # 4. Metadata provenance & recency (max 10)
    meta_score = 0
    if item.published_at:
        meta_score += 4
        try:
            pub_dt = datetime.fromisoformat(item.published_at.replace("Z", "+00:00"))
            age_hours = max(0.0, (now - pub_dt).total_seconds() / 3600.0)
            if age_hours <= 48:
                meta_score += 3
            elif age_hours <= 168:
                meta_score += 2
            else:
                meta_score += 1
        except ValueError:
            pass
    if item.authors:
        meta_score += 2
    if item.url.startswith("https://") and "news.google.com" not in item.source_domain:
        meta_score += 1
    meta_score = min(10, meta_score)

    total = max(0, min(100, auth_score + corr_score + evidence_score + meta_score - penalty))
    item.credibility_score = total
    item.credibility_tier = tier_from_score(total)
    item.credibility_notes = notes
    return item
