"""Automation & Robotics science/industry sources (arXiv, IEEE, Robot Report, HN, VN)."""

from __future__ import annotations

import asyncio
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from gemini_news_mcp.credibility import extract_domain
from gemini_news_mcp.http_client import fetch_json, fetch_text
from gemini_news_mcp.models import NewsItem, SourceStatus
from gemini_news_mcp.processing import sanitize_text
from gemini_news_mcp.sources.rss import fetch_rss_source, google_news_rss_url

ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}

SUBTOPIC_KEYWORDS: dict[str, re.Pattern[str]] = {
    "robotics": re.compile(r"\b(robot|humanoid|manipulator|drone|uav|autonomous|ros2|amr|agv|rô-bốt)\b", re.IGNORECASE),
    "industrial": re.compile(
        r"\b(plc|scada|factory|manufacturing|siemens|rockwell|abb|fanuc|kuka|iiot|industrial|công nghiệp|nhà máy|tự động hóa)\b",
        re.IGNORECASE,
    ),
    "control_ai": re.compile(
        r"\b(control|mpc|pid|reinforcement learning|vla|embodied|sensor|actuator|digital twin|điều khiển|cảm biến)\b",
        re.IGNORECASE,
    ),
}

VN_AUTOMATION_FILTER = re.compile(
    r"(tự động hóa|robot|rô-bốt|plc|scada|nhà máy|công nghiệp|điều khiển|cảm biến|bán dẫn|chip|ai\b|trí tuệ nhân tạo|xe tự lái|drone)",
    re.IGNORECASE,
)


def parse_arxiv_atom(xml_text: str, max_items: int = 12) -> list[NewsItem]:
    root = ET.fromstring(xml_text)
    items: list[NewsItem] = []
    for entry in root.findall("atom:entry", ARXIV_NS)[:max_items]:
        raw_id = (entry.findtext("atom:id", default="", namespaces=ARXIV_NS) or "").strip()
        title = sanitize_text(entry.findtext("atom:title", default="", namespaces=ARXIV_NS) or "", max_len=240)
        summary = sanitize_text(entry.findtext("atom:summary", default="", namespaces=ARXIV_NS) or "", max_len=400)
        published = (entry.findtext("atom:published", default="", namespaces=ARXIV_NS) or "").strip() or None
        authors = [
            sanitize_text(a.findtext("atom:name", default="", namespaces=ARXIV_NS) or "", max_len=60)
            for a in entry.findall("atom:author", ARXIV_NS)[:4]
        ]
        authors = [a for a in authors if a]

        arxiv_id = raw_id.rsplit("/", 1)[-1] if raw_id else ""
        url = raw_id.replace("http://", "https://") if raw_id else ""
        if not title or not url:
            continue

        items.append(
            NewsItem(
                title=title,
                url=url,
                source_name="arXiv",
                source_domain="arxiv.org",
                domain="automation",
                language="en",
                published_at=published,
                summary=summary,
                authors=authors,
                evidence_ids=[f"arXiv:{arxiv_id}"] if arxiv_id else [],
            )
        )
    return items


async def fetch_arxiv_automation(subtopic: str = "all", timeout: float = 7.0) -> tuple[list[NewsItem], SourceStatus]:
    t0 = time.monotonic()
    query_map = {
        "robotics": "cat:cs.RO",
        "industrial": "(cat:cs.RO OR cat:eess.SY) AND (industrial OR manufacturing OR automation)",
        "control_ai": "cat:eess.SY OR cat:cs.SY",
        "papers": "cat:cs.RO OR cat:eess.SY OR cat:cs.SY",
        "all": "cat:cs.RO OR cat:eess.SY",
    }
    search_query = query_map.get(subtopic, query_map["all"])
    url = "https://export.arxiv.org/api/query"
    params = {
        "search_query": search_query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": "12",
    }
    try:
        xml_text, _ = await fetch_text(url, timeout=timeout, params=params)
        items = parse_arxiv_atom(xml_text, max_items=12)
        return items, SourceStatus(
            name="arXiv (cs.RO/eess.SY)",
            ok=True,
            count=len(items),
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
    except Exception as exc:
        return [], SourceStatus(
            name="arXiv (cs.RO/eess.SY)",
            ok=False,
            count=0,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error=f"{type(exc).__name__}: {str(exc)[:140]}",
        )


async def fetch_hn_automation(days: int = 7, timeout: float = 7.0) -> tuple[list[NewsItem], SourceStatus]:
    t0 = time.monotonic()
    cutoff_ts = int(datetime.now(timezone.utc).timestamp()) - max(1, days) * 86400
    url = "https://hn.algolia.com/api/v1/search_by_date"
    try:
        r1, r2 = await asyncio.gather(
            fetch_json(
                url,
                timeout=timeout,
                params={
                    "query": "robotics",
                    "tags": "story",
                    "numericFilters": f"created_at_i>{cutoff_ts},points>=10",
                    "hitsPerPage": "8",
                },
            ),
            fetch_json(
                url,
                timeout=timeout,
                params={
                    "query": "automation",
                    "tags": "story",
                    "numericFilters": f"created_at_i>{cutoff_ts},points>=15",
                    "hitsPerPage": "8",
                },
            ),
        )
        hits = list(r1.get("hits", [])) + list(r2.get("hits", []))
        items: list[NewsItem] = []
        seen_ids: set[str] = set()
        for hit in hits:
            oid = str(hit.get("objectID") or "")
            if oid in seen_ids:
                continue
            seen_ids.add(oid)
            title = sanitize_text(hit.get("title", ""), max_len=240)
            story_url = (hit.get("url") or f"https://news.ycombinator.com/item?id={oid}").strip()
            if not title:
                continue
            points = hit.get("points", 0)
            comments = hit.get("num_comments", 0)
            domain = extract_domain(story_url) or "news.ycombinator.com"
            items.append(
                NewsItem(
                    title=title,
                    url=story_url,
                    source_name=f"Hacker News ({domain})",
                    source_domain=domain,
                    domain="automation",
                    language="en",
                    published_at=hit.get("created_at"),
                    summary=f"Thảo luận cộng đồng kỹ thuật: {points} points, {comments} comments trên Hacker News.",
                )
            )
        return items, SourceStatus(
            name="Hacker News (Automation)",
            ok=True,
            count=len(items),
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
    except Exception as exc:
        return [], SourceStatus(
            name="Hacker News (Automation)",
            ok=False,
            count=0,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error=f"{type(exc).__name__}: {str(exc)[:140]}",
        )


async def fetch_automation_sources(
    *,
    subtopic: str = "all",
    days: int = 7,
    language: str = "both",
    timeout: float = 7.0,
) -> tuple[list[NewsItem], list[SourceStatus]]:
    tasks = []
    if language in {"en", "both"}:
        tasks.append(fetch_arxiv_automation(subtopic=subtopic, timeout=timeout))
        if subtopic != "papers":
            tasks.extend(
                [
                    fetch_rss_source(
                        name="IEEE Spectrum Robotics",
                        url="https://spectrum.ieee.org/feeds/topic/robotics.rss",
                        domain="automation",
                        language="en",
                        timeout=timeout,
                    ),
                    fetch_rss_source(
                        name="ScienceDaily Robotics",
                        url="https://www.sciencedaily.com/rss/computers_math/robotics.xml",
                        domain="automation",
                        language="en",
                        timeout=timeout,
                    ),
                    fetch_rss_source(
                        name="Google News EN (Industrial Automation & Robotics)",
                        url=google_news_rss_url(
                            '("The Robot Report" OR "Automation World" OR "industrial automation" OR "humanoid robot" OR "PLC SCADA")',
                            "en",
                        ),
                        domain="automation",
                        language="en",
                        is_google_news=True,
                        timeout=timeout,
                    ),
                    fetch_hn_automation(days=days, timeout=timeout),
                ]
            )

    if language in {"vi", "both"} and subtopic != "papers":
        tasks.extend(
            [
                fetch_rss_source(
                    name="Google News VI (Tự động hóa)",
                    url=google_news_rss_url('"tự động hóa" OR robotics OR "nhà máy thông minh" OR PLC', "vi"),
                    domain="automation",
                    language="vi",
                    is_google_news=True,
                    timeout=timeout,
                ),
                fetch_rss_source(
                    name="VnExpress Khoa học",
                    url="https://vnexpress.net/rss/khoa-hoc-cong-nghe.rss",
                    domain="automation",
                    language="vi",
                    timeout=timeout,
                ),
            ]
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)
    all_items: list[NewsItem] = []
    statuses: list[SourceStatus] = []

    for res in results:
        if isinstance(res, Exception):
            statuses.append(SourceStatus(name="automation_task", ok=False, error=str(res)[:120]))
            continue
        items, status = res
        # Keep only automation-relevant articles from general VnExpress Science feed
        if status.name == "VnExpress Khoa học":
            items = [it for it in items if VN_AUTOMATION_FILTER.search(f"{it.title} {it.summary}")]
            status.count = len(items)
        all_items.extend(items)
        statuses.append(status)

    if subtopic in SUBTOPIC_KEYWORDS:
        pat = SUBTOPIC_KEYWORDS[subtopic]
        filtered = [it for it in all_items if pat.search(f"{it.title} {it.summary}")]
        if filtered:
            all_items = filtered

    return all_items, statuses
