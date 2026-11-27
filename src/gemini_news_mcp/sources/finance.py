"""Finance market movers (Yahoo Finance) + volatility driver news (Global & Vietnam)."""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from datetime import datetime, timezone

from gemini_news_mcp.config import DEFAULT_MARKET_SYMBOLS
from gemini_news_mcp.http_client import fetch_json
from gemini_news_mcp.models import MarketMover, NewsItem, SourceStatus
from gemini_news_mcp.sources.rss import fetch_rss_source, google_news_rss_url


def parse_yahoo_chart(symbol: str, name: str, market: str, data: dict) -> MarketMover:
    result_list = (data.get("chart") or {}).get("result") or []
    if not result_list:
        err = ((data.get("chart") or {}).get("error") or {}).get("description") or "No chart data"
        return MarketMover(
            symbol=symbol,
            name=name,
            market=market,
            currency="",
            price=None,
            change_1d_pct=None,
            change_5d_pct=None,
            error=str(err),
        )

    entry = result_list[0]
    meta = entry.get("meta") or {}
    currency = str(meta.get("currency") or "")
    closes_raw = (((entry.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    closes = [float(c) for c in closes_raw if c is not None]

    price = meta.get("regularMarketPrice")
    if price is None and closes:
        price = closes[-1]
    price_val = round(float(price), 4) if price is not None else None

    prev_close = meta.get("chartPreviousClose")
    change_1d: float | None = None
    if price_val is not None and len(closes) >= 2 and closes[-2] != 0:
        change_1d = round(((price_val - closes[-2]) / closes[-2]) * 100.0, 2)
    elif price_val is not None and prev_close not in (None, 0):
        change_1d = round(((price_val - float(prev_close)) / float(prev_close)) * 100.0, 2)

    change_5d: float | None = None
    if price_val is not None and len(closes) >= 5 and closes[-5] != 0:
        change_5d = round(((price_val - closes[-5]) / closes[-5]) * 100.0, 2)
    elif price_val is not None and len(closes) >= 2 and closes[0] != 0:
        change_5d = round(((price_val - closes[0]) / closes[0]) * 100.0, 2)

    market_ts = meta.get("regularMarketTime")
    as_of = (
        datetime.fromtimestamp(int(market_ts), tz=timezone.utc).isoformat()
        if market_ts
        else datetime.now(timezone.utc).isoformat()
    )

    return MarketMover(
        symbol=symbol,
        name=meta.get("shortName") or name,
        market=market,
        currency=currency,
        price=price_val,
        change_1d_pct=change_1d,
        change_5d_pct=change_5d,
        as_of=as_of,
    )


async def fetch_yahoo_mover(symbol: str, name: str, market: str, timeout: float = 7.0) -> MarketMover:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"range": "10d", "interval": "1d"}
    try:
        data = await fetch_json(url, timeout=timeout, params=params)
        return parse_yahoo_chart(symbol, name, market, data)
    except Exception as exc:
        return MarketMover(
            symbol=symbol,
            name=name,
            market=market,
            currency="",
            price=None,
            change_1d_pct=None,
            change_5d_pct=None,
            error=f"{type(exc).__name__}: {str(exc)[:120]}",
        )


async def fetch_finance_sources(
    *,
    market: str = "all",
    symbols: list[str] | None = None,
    language: str = "both",
    timeout: float = 7.0,
) -> tuple[list[MarketMover], list[NewsItem], list[SourceStatus]]:
    # 1. Select symbols to quote
    target_symbols: list[tuple[str, str, str]] = []
    if symbols:
        for sym in symbols[:8]:
            clean = sym.strip().upper()
            if clean:
                target_symbols.append((clean, clean, "custom"))
    elif market in DEFAULT_MARKET_SYMBOLS:
        target_symbols = list(DEFAULT_MARKET_SYMBOLS[market])
    else:
        for group in DEFAULT_MARKET_SYMBOLS.values():
            target_symbols.extend(group)

    mover_tasks = [fetch_yahoo_mover(sym, name, mkt, timeout=timeout) for sym, name, mkt in target_symbols]

    # 2. Select financial driver news feeds
    news_tasks = []
    symbol_query_en = (
        " OR ".join(sym for sym, _, _ in target_symbols[:4])
        if symbols
        else 'stock market OR "Federal Reserve" OR inflation OR gold OR oil'
    )
    symbol_query_vi = (
        " OR ".join(sym.replace(".VN", "") for sym, _, _ in target_symbols[:4])
        if symbols
        else '"VN-Index" OR "giá vàng" OR "tỷ giá USD" OR "lãi suất" OR chứng khoán'
    )

    if language in {"en", "both"} and market != "vn":
        news_tasks.extend(
            [
                fetch_rss_source(
                    name="CNBC Finance",
                    url="https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
                    domain="finance",
                    language="en",
                    timeout=timeout,
                ),
                fetch_rss_source(
                    name="MarketWatch",
                    url="https://feeds.content.dowjones.io/public/rss/mw_topstories",
                    domain="finance",
                    language="en",
                    timeout=timeout,
                ),
                fetch_rss_source(
                    name="Yahoo Finance News",
                    url="https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC,GC=F,BTC-USD&region=US&lang=en-US",
                    domain="finance",
                    language="en",
                    timeout=timeout,
                ),
                fetch_rss_source(
                    name="Google News EN (Market Drivers)",
                    url=google_news_rss_url(f"({symbol_query_en}) (why OR surge OR drop OR rally OR Fed OR earnings)", "en"),
                    domain="finance",
                    language="en",
                    is_google_news=True,
                    timeout=timeout,
                ),
            ]
        )

    if language in {"vi", "both"} and (market in {"all", "vn", "commodities"} or symbols):
        news_tasks.extend(
            [
                fetch_rss_source(
                    name="VnExpress Kinh doanh",
                    url="https://vnexpress.net/rss/kinh-doanh.rss",
                    domain="finance",
                    language="vi",
                    timeout=timeout,
                ),
                fetch_rss_source(
                    name="CafeF Chứng khoán",
                    url="https://m.cafef.vn/thi-truong-chung-khoan.rss",
                    domain="finance",
                    language="vi",
                    timeout=timeout,
                ),
                fetch_rss_source(
                    name="Vietstock",
                    url="https://vietstock.vn/830/chung-khoan/co-phieu.rss",
                    domain="finance",
                    language="vi",
                    timeout=timeout,
                ),
                fetch_rss_source(
                    name="Google News VI (Nguyên nhân biến động tài chính)",
                    url=google_news_rss_url(f"({symbol_query_vi}) (biến động OR tăng OR giảm OR nguyên nhân)", "vi"),
                    domain="finance",
                    language="vi",
                    is_google_news=True,
                    timeout=timeout,
                ),
            ]
        )

    movers_raw, news_raw = await asyncio.gather(
        asyncio.gather(*mover_tasks, return_exceptions=True),
        asyncio.gather(*news_tasks, return_exceptions=True),
    )

    movers: list[MarketMover] = []
    ok_movers = 0
    for m in movers_raw:
        if isinstance(m, MarketMover):
            movers.append(m)
            if m.price is not None:
                ok_movers += 1

    statuses: list[SourceStatus] = [
        SourceStatus(
            name="Yahoo Finance Market Quotes",
            ok=ok_movers > 0,
            count=ok_movers,
            error=None if ok_movers > 0 else "No quotes returned",
        )
    ]

    all_items: list[NewsItem] = []
    for res in news_raw:
        if isinstance(res, Exception):
            statuses.append(SourceStatus(name="finance_news_task", ok=False, error=str(res)[:120]))
            continue
        items, status = res
        all_items.extend(items)
        statuses.append(status)

    return movers, all_items, statuses


def summarize_volatility_drivers(items: list[NewsItem]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for it in items:
        for tag in it.driver_tags:
            counts[tag] += 1
    return dict(counts.most_common())
