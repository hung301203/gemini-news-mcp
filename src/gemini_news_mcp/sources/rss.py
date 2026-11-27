"""Shared RSS/Atom parser and Google News RSS helpers."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

import feedparser

from gemini_news_mcp.credibility import extract_domain
from gemini_news_mcp.http_client import fetch_text
from gemini_news_mcp.models import NewsItem, SourceStatus
from gemini_news_mcp.processing import sanitize_text


def google_news_rss_url(query: str, language: str = "en") -> str:
    encoded = quote_plus(query)
    if language == "vi":
        return f"https://news.google.com/rss/search?q={encoded}&hl=vi&gl=VN&ceid=VN:vi"
    return f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"


def _entry_published_iso(entry: dict) -> str | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        dt = datetime(*parsed[:6], tzinfo=timezone.utc)
        return dt.isoformat()
    except (TypeError, ValueError):
        return None


def parse_rss_xml(
    xml_text: str,
    *,
    source_name: str,
    domain: str,
    language: str = "en",
    is_google_news: bool = False,
    max_items: int = 18,
) -> list[NewsItem]:
    feed = feedparser.parse(xml_text)
    items: list[NewsItem] = []

    for entry in feed.entries[:max_items]:
        title = sanitize_text(entry.get("title", ""), max_len=240)
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue

        item_source_name = source_name
        item_domain = extract_domain(link)

        # For Google News RSS, extract real publisher name and domain from <source>
        if is_google_news:
            src_meta = entry.get("source")
            if isinstance(src_meta, dict):
                pub_title = sanitize_text(src_meta.get("title", ""), max_len=80)
                pub_href = (src_meta.get("href") or "").strip()
                if pub_title:
                    item_source_name = pub_title
                    suffix = f" - {pub_title}"
                    if title.endswith(suffix):
                        title = title[: -len(suffix)].strip()
                if pub_href:
                    extracted = extract_domain(pub_href)
                    if extracted:
                        item_domain = extracted

        summary = sanitize_text(
            entry.get("summary") or entry.get("description") or "",
            max_len=400,
        )
        authors: list[str] = []
        if entry.get("author"):
            authors.append(sanitize_text(entry["author"], max_len=80))

        items.append(
            NewsItem(
                title=title,
                url=link,
                source_name=item_source_name,
                source_domain=item_domain,
                domain=domain,
                language=language,
                published_at=_entry_published_iso(entry),
                summary=summary,
                authors=authors,
            )
        )

    return items


async def fetch_rss_source(
    *,
    name: str,
    url: str,
    domain: str,
    language: str = "en",
    is_google_news: bool = False,
    timeout: float = 7.0,
    max_items: int = 18,
) -> tuple[list[NewsItem], SourceStatus]:
    t0 = time.monotonic()
    try:
        xml_text, _ = await fetch_text(url, timeout=timeout, max_bytes=1_200_000)
        items = parse_rss_xml(
            xml_text,
            source_name=name,
            domain=domain,
            language=language,
            is_google_news=is_google_news,
            max_items=max_items,
        )
        return items, SourceStatus(
            name=name,
            ok=True,
            count=len(items),
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
    except Exception as exc:
        return [], SourceStatus(
            name=name,
            ok=False,
            count=0,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error=f"{type(exc).__name__}: {str(exc)[:140]}",
        )
