"""Unit tests for source parsers (Google News RSS, arXiv Atom, Yahoo Finance, PubMed)."""

from gemini_news_mcp.sources.automation import parse_arxiv_atom
from gemini_news_mcp.sources.finance import parse_yahoo_chart
from gemini_news_mcp.sources.rss import parse_rss_xml
from gemini_news_mcp.sources.wellness import parse_pubmed_summary


def test_parse_google_news_rss_extracts_real_publisher_domain() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>Google News</title>
      <item>
        <title>VN-Index hồi phục mạnh nhờ nhóm ngân hàng - VnExpress</title>
        <link>https://news.google.com/rss/articles/CBMi123</link>
        <pubDate>Fri, 27 Nov 2026 07:00:00 GMT</pubDate>
        <source url="https://vnexpress.net">VnExpress</source>
        <description>Thị trường chứng khoán tăng điểm tích cực.</description>
      </item>
    </channel></rss>"""
    items = parse_rss_xml(xml, source_name="Google News VI", domain="finance", language="vi", is_google_news=True)
    assert len(items) == 1
    assert items[0].source_name == "VnExpress"
    assert items[0].source_domain == "vnexpress.net"
    assert items[0].title == "VN-Index hồi phục mạnh nhờ nhóm ngân hàng"


def test_parse_arxiv_atom_extracts_id_and_authors() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2611.12345v1</id>
        <published>2026-11-26T18:00:00Z</published>
        <title>Adaptive Model Predictive Control for Industrial Manipulators</title>
        <summary>We propose an adaptive MPC scheme for high-speed robotic assembly.</summary>
        <author><name>Tran Minh</name></author>
      </entry>
    </feed>"""
    items = parse_arxiv_atom(xml)
    assert len(items) == 1
    assert items[0].evidence_ids == ["arXiv:2611.12345v1"]
    assert items[0].url == "https://arxiv.org/abs/2611.12345v1"
    assert items[0].authors == ["Tran Minh"]


def test_parse_yahoo_chart_computes_1d_and_5d_changes() -> None:
    sample = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "currency": "USD",
                        "shortName": "Gold Futures",
                        "regularMarketPrice": 2700.0,
                        "regularMarketTime": 1795700000,
                    },
                    "indicators": {
                        "quote": [
                            {"close": [2500.0, 2550.0, 2600.0, 2650.0, 2700.0]}
                        ]
                    },
                }
            ]
        }
    }
    mover = parse_yahoo_chart("GC=F", "Gold Futures", "commodities", sample)
    assert mover.price == 2700.0
    assert mover.change_1d_pct == 1.89
    assert mover.change_5d_pct == 8.0
    assert mover.error is None


def test_parse_pubmed_summary_extracts_pmid_and_journal() -> None:
    sample = {
        "result": {
            "uids": ["40123456"],
            "40123456": {
                "title": "Effects of Zone 2 aerobic training on metabolic health.",
                "fulljournalname": "Journal of Applied Physiology",
                "sortpubdate": "2026/11/20 00:00",
                "authors": [{"name": "Le H"}],
                "pubtype": ["Journal Article", "Randomized Controlled Trial"],
            },
        }
    }
    items = parse_pubmed_summary(sample)
    assert len(items) == 1
    assert items[0].evidence_ids == ["PMID:40123456"]
    assert items[0].source_domain == "pubmed.ncbi.nlm.nih.gov"
    assert items[0].published_at == "2026-11-20T00:00:00+00:00"
