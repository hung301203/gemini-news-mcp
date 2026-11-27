"""Configuration, environment settings, and domain credibility registry."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    port: int = 8000
    mcp_path_secret: str = ""
    cache_ttl_seconds: int = 600
    rate_limit_rpm: int = 60
    source_timeout_seconds: float = 7.0
    max_article_bytes: int = 1_500_000
    max_article_chars: int = 6_000

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            port=int(os.getenv("PORT", "8000")),
            mcp_path_secret=os.getenv("MCP_PATH_SECRET", "").strip().strip("/"),
            cache_ttl_seconds=max(30, int(os.getenv("CACHE_TTL_SECONDS", "600"))),
            rate_limit_rpm=max(5, int(os.getenv("RATE_LIMIT_RPM", "60"))),
            source_timeout_seconds=max(2.0, float(os.getenv("SOURCE_TIMEOUT_SECONDS", "7.0"))),
        )

    @property
    def mcp_route_path(self) -> str:
        if self.mcp_path_secret:
            return f"/mcp/{self.mcp_path_secret}"
        return "/mcp"


# Domain authority registry: host -> (authority_score_out_of_50, source_type, display_name)
DOMAIN_AUTHORITY: dict[str, tuple[int, str, str]] = {
    # Tier 1: Academic, official institutions, primary wires & market data (45-50)
    "pubmed.ncbi.nlm.nih.gov": (50, "academic", "PubMed (NIH)"),
    "ncbi.nlm.nih.gov": (50, "academic", "NCBI / NIH"),
    "nih.gov": (49, "official", "NIH"),
    "who.int": (49, "official", "WHO"),
    "nature.com": (50, "academic", "Nature"),
    "science.org": (50, "academic", "Science"),
    "thelancet.com": (50, "academic", "The Lancet"),
    "nejm.org": (50, "academic", "NEJM"),
    "arxiv.org": (48, "academic", "arXiv"),
    "ieeexplore.ieee.org": (49, "academic", "IEEE Xplore"),
    "spectrum.ieee.org": (47, "trade_science", "IEEE Spectrum"),
    "health.harvard.edu": (48, "medical_institution", "Harvard Health"),
    "mayoclinic.org": (48, "medical_institution", "Mayo Clinic"),
    "news.mit.edu": (47, "academic_news", "MIT News"),
    "federalreserve.gov": (50, "official", "Federal Reserve"),
    "imf.org": (49, "official", "IMF"),
    "worldbank.org": (49, "official", "World Bank"),
    "sbv.gov.vn": (49, "official", "Ngân hàng Nhà nước VN"),
    "reuters.com": (48, "wire", "Reuters"),
    "apnews.com": (47, "wire", "Associated Press"),
    "bloomberg.com": (47, "major_finance", "Bloomberg"),
    "ft.com": (47, "major_finance", "Financial Times"),
    "wsj.com": (46, "major_finance", "Wall Street Journal"),
    "finance.yahoo.com": (44, "market_data", "Yahoo Finance"),
    # Tier 2: Reputable domain-specific trade, science, finance, and mainstream VN press (36-42)
    "therobotreport.com": (41, "trade_science", "The Robot Report"),
    "automationworld.com": (41, "trade_science", "Automation World"),
    "controleng.com": (41, "trade_science", "Control Engineering"),
    "roboticsandautomationnews.com": (38, "trade_science", "Robotics & Automation News"),
    "sciencedaily.com": (42, "science_news", "ScienceDaily"),
    "medicalnewstoday.com": (39, "medical_media", "Medical News Today"),
    "healthline.com": (37, "medical_media", "Healthline"),
    "cnbc.com": (41, "major_finance", "CNBC"),
    "marketwatch.com": (40, "major_finance", "MarketWatch"),
    "investing.com": (38, "major_finance", "Investing.com"),
    "economist.com": (44, "major_finance", "The Economist"),
    "thesaigontimes.vn": (41, "finance_vn", "Kinh tế Sài Gòn"),
    "vneconomy.vn": (40, "finance_vn", "VnEconomy"),
    "vietstock.vn": (40, "finance_vn", "Vietstock"),
    "vnexpress.net": (40, "major_vn", "VnExpress"),
    "cafef.vn": (39, "finance_vn", "CafeF"),
    "baodautu.vn": (39, "finance_vn", "Báo Đầu Tư"),
    "tuoitre.vn": (39, "major_vn", "Tuổi Trẻ"),
    "thanhnien.vn": (38, "major_vn", "Thanh Niên"),
    "vietnamplus.vn": (40, "major_vn", "VietnamPlus (TTXVN)"),
    "techcrunch.com": (38, "tech_media", "TechCrunch"),
    "arstechnica.com": (40, "tech_media", "Ars Technica"),
    # Tier 3: Community & aggregators (22-32)
    "news.ycombinator.com": (30, "tech_community", "Hacker News"),
    "github.com": (33, "primary_code", "GitHub"),
    "reddit.com": (22, "community", "Reddit"),
}

# Publisher name aliases for Google News <source> text fallback
PUBLISHER_ALIASES: dict[str, str] = {
    "reuters": "reuters.com",
    "bloomberg": "bloomberg.com",
    "financial times": "ft.com",
    "wall street journal": "wsj.com",
    "cnbc": "cnbc.com",
    "marketwatch": "marketwatch.com",
    "yahoo finance": "finance.yahoo.com",
    "ieee spectrum": "spectrum.ieee.org",
    "the robot report": "therobotreport.com",
    "automation world": "automationworld.com",
    "harvard health": "health.harvard.edu",
    "sciencedaily": "sciencedaily.com",
    "medical news today": "medicalnewstoday.com",
    "vnexpress": "vnexpress.net",
    "cafef": "cafef.vn",
    "vietstock": "vietstock.vn",
    "vneconomy": "vneconomy.vn",
    "tuổi trẻ": "tuoitre.vn",
    "thanh niên": "thanhnien.vn",
    "báo đầu tư": "baodautu.vn",
    "vietnamplus": "vietnamplus.vn",
    "kinh tế sài gòn": "thesaigontimes.vn",
    "kinh tế sài gòn online": "thesaigontimes.vn",
}

DEFAULT_MARKET_SYMBOLS: dict[str, list[tuple[str, str, str]]] = {
    "us": [
        ("^GSPC", "S&P 500", "us"),
        ("^IXIC", "Nasdaq Composite", "us"),
        ("DX-Y.NYB", "US Dollar Index (DXY)", "us"),
    ],
    "vn": [
        ("E1VFVN30.VN", "VN30 ETF (HOSE Proxy)", "vn"),
        ("VNM", "VanEck Vietnam ETF", "vn"),
        ("USDVND=X", "USD/VND", "vn"),
    ],
    "commodities": [
        ("GC=F", "Gold Futures", "commodities"),
        ("CL=F", "WTI Crude Oil", "commodities"),
    ],
    "crypto": [
        ("BTC-USD", "Bitcoin", "crypto"),
        ("ETH-USD", "Ethereum", "crypto"),
    ],
}
