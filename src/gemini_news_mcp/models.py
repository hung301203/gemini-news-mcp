"""Normalized data models for news items, market movers, and source telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NewsItem:
    title: str
    url: str
    source_name: str
    source_domain: str
    domain: str  # automation | finance | wellness | general
    language: str = "en"  # en | vi
    published_at: str | None = None  # ISO-8601 UTC
    summary: str = ""
    authors: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)  # e.g. PMID:..., arXiv:...
    driver_tags: list[str] = field(default_factory=list)
    corroborated_by: list[str] = field(default_factory=list)
    credibility_score: int = 0
    credibility_tier: str = "Low"
    credibility_notes: list[str] = field(default_factory=list)
    extra_links: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": self.title,
            "url": self.url,
            "source": self.source_name,
            "source_domain": self.source_domain,
            "domain": self.domain,
            "language": self.language,
            "published_at": self.published_at,
            "summary": self.summary,
            "credibility_score": self.credibility_score,
            "credibility_tier": self.credibility_tier,
            "corroboration_count": 1 + len(self.corroborated_by),
            "credibility_notes": self.credibility_notes,
        }
        if self.corroborated_by:
            payload["corroborated_by"] = self.corroborated_by
        if self.authors:
            payload["authors"] = self.authors[:5]
        if self.evidence_ids:
            payload["evidence_ids"] = self.evidence_ids
        if self.driver_tags:
            payload["driver_tags"] = self.driver_tags
        return payload


@dataclass
class MarketMover:
    symbol: str
    name: str
    market: str
    currency: str
    price: float | None
    change_1d_pct: float | None
    change_5d_pct: float | None
    as_of: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "currency": self.currency,
            "price": self.price,
            "change_1d_pct": self.change_1d_pct,
            "change_5d_pct": self.change_5d_pct,
            "as_of": self.as_of,
        }
        if self.error:
            data["error"] = self.error
        return data


@dataclass
class SourceStatus:
    name: str
    ok: bool
    count: int = 0
    latency_ms: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "ok": self.ok,
            "count": self.count,
            "latency_ms": self.latency_ms,
        }
        if self.error:
            data["error"] = self.error
        return data
