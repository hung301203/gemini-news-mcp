"""Evidence-based Wellness sources (PubMed, Harvard Health, ScienceDaily, VnExpress)."""

from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone

from gemini_news_mcp.http_client import fetch_json
from gemini_news_mcp.models import NewsItem, SourceStatus
from gemini_news_mcp.processing import sanitize_text
from gemini_news_mcp.sources.rss import fetch_rss_source, google_news_rss_url

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

FOCUS_PUBMED_TERMS: dict[str, str] = {
    "sleep": '(sleep quality[Title/Abstract] OR insomnia[Title/Abstract] OR circadian[Title/Abstract]) AND humans[MeSH Terms] AND (randomized controlled trial[pt] OR meta-analysis[pt])',
    "nutrition": '(mediterranean diet[Title/Abstract] OR dietary fiber[Title/Abstract] OR protein intake[Title/Abstract] OR gut microbiome[Title/Abstract]) AND humans[MeSH Terms] AND (randomized controlled trial[pt] OR meta-analysis[pt])',
    "exercise": '(resistance training[Title/Abstract] OR aerobic exercise[Title/Abstract] OR physical activity[Title/Abstract]) AND humans[MeSH Terms] AND (randomized controlled trial[pt] OR meta-analysis[pt])',
    "mental_health": '(stress reduction[Title/Abstract] OR mindfulness[Title/Abstract] OR burnout[Title/Abstract] OR anxiety[Title/Abstract]) AND humans[MeSH Terms] AND (randomized controlled trial[pt] OR meta-analysis[pt])',
    "research": '(sleep[Title/Abstract] OR nutrition[Title/Abstract] OR exercise[Title/Abstract] OR longevity[Title/Abstract]) AND humans[MeSH Terms] AND (randomized controlled trial[pt] OR meta-analysis[pt])',
    "all": '(sleep quality[Title/Abstract] OR physical activity[Title/Abstract] OR mediterranean diet[Title/Abstract] OR stress reduction[Title/Abstract]) AND humans[MeSH Terms] AND (randomized controlled trial[pt] OR meta-analysis[pt])',
}

FOCUS_KEYWORDS: dict[str, re.Pattern[str]] = {
    "sleep": re.compile(r"\b(sleep|insomnia|circadian|melatonin|giấc ngủ|mất ngủ|ngủ sâu)\b", re.IGNORECASE),
    "nutrition": re.compile(r"\b(diet|nutrition|protein|fiber|gut|sugar|dinh dưỡng|ăn uống|thực phẩm|đường huyết)\b", re.IGNORECASE),
    "exercise": re.compile(r"\b(exercise|workout|walking|strength|cardio|running|vận động|tập luyện|thể dục|chạy bộ)\b", re.IGNORECASE),
    "mental_health": re.compile(r"\b(stress|anxiety|mental|mindfulness|depression|burnout|tinh thần|căng thẳng|lo âu|thiền)\b", re.IGNORECASE),
}


def parse_pubmed_summary(summary_json: dict) -> list[NewsItem]:
    result = summary_json.get("result") or {}
    uids = result.get("uids") or []
    items: list[NewsItem] = []

    for uid in uids:
        doc = result.get(str(uid))
        if not isinstance(doc, dict):
            continue
        title = sanitize_text(doc.get("title", ""), max_len=240).rstrip(".")
        if not title:
            continue
        journal = sanitize_text(doc.get("fulljournalname") or doc.get("source") or "PubMed", max_len=100)
        pubdate_raw = str(doc.get("sortpubdate") or doc.get("pubdate") or "").strip()
        published_iso: str | None = None
        m = re.match(r"(\d{4})/(\d{2})/(\d{2})", pubdate_raw)
        if m:
            try:
                published_iso = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc).isoformat()
            except ValueError:
                published_iso = None

        authors = [
            sanitize_text(a.get("name", ""), max_len=60)
            for a in (doc.get("authors") or [])[:4]
            if isinstance(a, dict) and a.get("name")
        ]
        pubtypes = [str(pt) for pt in (doc.get("pubtype") or [])[:3]]
        summary = f"Tạp chí: {journal}."
        if pubtypes:
            summary += f" Loại nghiên cứu: {', '.join(pubtypes)}."

        items.append(
            NewsItem(
                title=title,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
                source_name=f"PubMed — {journal}",
                source_domain="pubmed.ncbi.nlm.nih.gov",
                domain="wellness",
                language="en",
                published_at=published_iso,
                summary=summary,
                authors=authors,
                evidence_ids=[f"PMID:{uid}"],
            )
        )
    return items


async def fetch_pubmed_wellness(focus: str = "all", days: int = 30, timeout: float = 7.0) -> tuple[list[NewsItem], SourceStatus]:
    t0 = time.monotonic()
    term = FOCUS_PUBMED_TERMS.get(focus, FOCUS_PUBMED_TERMS["all"])
    # PubMed indexing lags a few days, so keep minimum 30-day reldate for fresh studies
    reldate = max(30, min(180, days * 4))
    try:
        search_data = await fetch_json(
            f"{PUBMED_BASE}/esearch.fcgi",
            timeout=timeout,
            params={
                "db": "pubmed",
                "term": term,
                "retmode": "json",
                "retmax": "8",
                "sort": "pub date",
                "reldate": str(reldate),
                "datetype": "pdat",
            },
        )
        id_list = (search_data.get("esearchresult") or {}).get("idlist") or []
        if not id_list:
            return [], SourceStatus(
                name="PubMed (NIH)",
                ok=True,
                count=0,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

        summary_data = await fetch_json(
            f"{PUBMED_BASE}/esummary.fcgi",
            timeout=timeout,
            params={"db": "pubmed", "id": ",".join(id_list), "retmode": "json"},
        )
        items = parse_pubmed_summary(summary_data)
        return items, SourceStatus(
            name="PubMed (NIH)",
            ok=True,
            count=len(items),
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
    except Exception as exc:
        return [], SourceStatus(
            name="PubMed (NIH)",
            ok=False,
            count=0,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error=f"{type(exc).__name__}: {str(exc)[:140]}",
        )


async def fetch_wellness_sources(
    *,
    focus: str = "all",
    days: int = 7,
    language: str = "both",
    timeout: float = 7.0,
) -> tuple[list[NewsItem], list[SourceStatus]]:
    tasks = []
    if language in {"en", "both"}:
        tasks.append(fetch_pubmed_wellness(focus=focus, days=days, timeout=timeout))
        if focus != "research":
            tasks.extend(
                [
                    fetch_rss_source(
                        name="ScienceDaily Health",
                        url="https://www.sciencedaily.com/rss/health_medicine.xml",
                        domain="wellness",
                        language="en",
                        timeout=timeout,
                    ),
                    fetch_rss_source(
                        name="ScienceDaily Mind & Brain",
                        url="https://www.sciencedaily.com/rss/mind_brain.xml",
                        domain="wellness",
                        language="en",
                        timeout=timeout,
                    ),
                    fetch_rss_source(
                        name="ScienceDaily Nutrition",
                        url="https://www.sciencedaily.com/rss/health_medicine/nutrition.xml",
                        domain="wellness",
                        language="en",
                        timeout=timeout,
                    ),
                    fetch_rss_source(
                        name="Google News EN (Wellness Evidence)",
                        url=google_news_rss_url(
                            '("Harvard Health" OR "Mayo Clinic" OR study) (sleep OR nutrition OR exercise OR mental health)',
                            "en",
                        ),
                        domain="wellness",
                        language="en",
                        is_google_news=True,
                        timeout=timeout,
                    ),
                ]
            )

    if language in {"vi", "both"} and focus != "research":
        tasks.extend(
            [
                fetch_rss_source(
                    name="VnExpress Sức khỏe",
                    url="https://vnexpress.net/rss/suc-khoe.rss",
                    domain="wellness",
                    language="vi",
                    timeout=timeout,
                ),
                fetch_rss_source(
                    name="Google News VI (Sức khỏe & Wellness)",
                    url=google_news_rss_url(
                        '(giấc ngủ OR dinh dưỡng OR vận động OR "sức khỏe tinh thần") (nghiên cứu OR bác sĩ OR khoa học)',
                        "vi",
                    ),
                    domain="wellness",
                    language="vi",
                    is_google_news=True,
                    timeout=timeout,
                ),
            ]
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)
    all_items: list[NewsItem] = []
    statuses: list[SourceStatus] = []

    for res in results:
        if isinstance(res, Exception):
            statuses.append(SourceStatus(name="wellness_task", ok=False, error=str(res)[:120]))
            continue
        items, status = res
        all_items.extend(items)
        statuses.append(status)

    if focus in FOCUS_KEYWORDS:
        pat = FOCUS_KEYWORDS[focus]
        filtered = [it for it in all_items if pat.search(f"{it.title} {it.summary}")]
        if filtered:
            all_items = filtered

    return all_items, statuses
