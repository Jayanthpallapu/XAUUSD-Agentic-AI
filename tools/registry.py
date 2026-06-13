import logging
from fastmcp import FastMCP

# Market Data Tools
from tools.definitions.market_data import (
    fetch_gold_price,
    fetch_forex_prices,
    fetch_commodities_prices,
    fetch_crypto_prices,
    fetch_market_indices,
    fetch_treasury_yields,
    fetch_finnhub_news,
    fetch_alpha_vantage_sentiment,
)

# News & Calendar Tools
from tools.definitions.news_calendar import (
    fetch_news_rss,
    analyze_news_sentiment,
    fetch_economic_calendar,
)

# Technical Analysis Tools
from tools.definitions.technical_analysis import (
    fetch_ohlcv_data,
    analyze_price_structure,
)

# Trading Performance Tools
from tools.definitions.trading_performance import (
    execute_paper_trade,
    fetch_trade_performance,
    record_teacher_feedback,
)

# System Tools
from tools.definitions.system import (
    check_agent_health,
    restart_agent_node,
    send_telegram_notification,
    send_telegram_trade_signal,
)

# Web Scraper Tools
from tools.definitions.web_scraper import (
    scrape_kitco_news,
    scrape_forex_factory_calendar,
)

logger = logging.getLogger("mcp_registry")

# Initialize FastMCP Server
mcp = FastMCP("XAUUSD Agentic Company Toolset")


# ─────────────────────────────────────────────
# 1. Market Data Tools
# ─────────────────────────────────────────────

@mcp.tool(name="fetch_gold_price", description="Fetches the current spot price of Gold (XAUUSD) in USD via Twelve Data or yfinance.")
def mcp_fetch_gold_price() -> str:
    return fetch_gold_price.func()


@mcp.tool(name="fetch_forex_prices", description="Fetches exchange rates for currency pairs. Input format: 'EURUSD,USDJPY'.")
def mcp_fetch_forex_prices(pairs: str = "EURUSD,USDJPY,GBPUSD,USDCHF,AUDUSD") -> str:
    return fetch_forex_prices.func(pairs=pairs)


@mcp.tool(name="fetch_commodities_prices", description="Fetches prices of Silver, WTI Crude Oil, Brent, and Copper.")
def mcp_fetch_commodities_prices() -> str:
    return fetch_commodities_prices.func()


@mcp.tool(name="fetch_crypto_prices", description="Fetches the current spot price of Bitcoin (BTC) in USD.")
def mcp_fetch_crypto_prices() -> str:
    return fetch_crypto_prices.func()


@mcp.tool(name="fetch_market_indices", description="Fetches US Dollar Index (DXY), S&P 500, and VIX values.")
def mcp_fetch_market_indices() -> str:
    return fetch_market_indices.func()


@mcp.tool(name="fetch_treasury_yields", description="Fetches US 10-Year and 2-Year Treasury Yields via FRED API.")
def mcp_fetch_treasury_yields() -> str:
    return fetch_treasury_yields.func()


@mcp.tool(name="fetch_finnhub_news", description="Fetches latest gold and forex news headlines from Finnhub professional data feed.")
def mcp_fetch_finnhub_news() -> str:
    return fetch_finnhub_news.func()


@mcp.tool(name="fetch_alpha_vantage_sentiment", description="Fetches gold and forex news sentiment scores from Alpha Vantage.")
def mcp_fetch_alpha_vantage_sentiment() -> str:
    return fetch_alpha_vantage_sentiment.func()


# ─────────────────────────────────────────────
# 2. News & Economic Calendar Tools
# ─────────────────────────────────────────────

@mcp.tool(name="fetch_news_rss", description="Fetches latest financial RSS news. Query can be 'gold FOMC inflation'.")
def mcp_fetch_news_rss(query: str = "gold price XAUUSD forex") -> str:
    return fetch_news_rss.func(query=query)


@mcp.tool(name="analyze_news_sentiment", description="Retrieves overall gold news sentiment stats and headlines.")
def mcp_analyze_news_sentiment() -> str:
    return analyze_news_sentiment.func()


@mcp.tool(name="fetch_economic_calendar", description="Retrieves economic calendar highlighting NFP, FOMC, CPI events via FMP API.")
def mcp_fetch_economic_calendar() -> str:
    return fetch_economic_calendar.func()


# ─────────────────────────────────────────────
# 3. Technical Analysis Tools (NEW)
# ─────────────────────────────────────────────

@mcp.tool(name="fetch_ohlcv_data", description="Fetches OHLCV candlestick data for XAU/USD at a given timeframe (1W, 1D, 4H, 1H, 15M, 5M) via Twelve Data.")
def mcp_fetch_ohlcv_data(timeframe: str = "1H", bars: int = 50) -> str:
    return fetch_ohlcv_data.func(timeframe=timeframe, bars=bars)


@mcp.tool(name="analyze_price_structure", description="Analyzes OHLCV data to identify trend, market structure, order blocks, liquidity zones, and candlestick patterns.")
def mcp_analyze_price_structure(ohlcv_json: str, timeframe: str = "1H") -> str:
    return analyze_price_structure.func(ohlcv_json=ohlcv_json, timeframe=timeframe)


# ─────────────────────────────────────────────
# 4. Web Scraper Tools
# ─────────────────────────────────────────────

@mcp.tool(name="scrape_kitco_news", description="Scrapes the latest gold market news from Kitco News with sentiment labels.")
def mcp_scrape_kitco_news() -> str:
    return scrape_kitco_news.func()


@mcp.tool(name="scrape_forex_factory_calendar", description="Scrapes today's Forex Factory economic calendar for high-impact USD events.")
def mcp_scrape_forex_factory_calendar() -> str:
    return scrape_forex_factory_calendar.func()


# ─────────────────────────────────────────────
# 5. Trading Performance Tools
# ─────────────────────────────────────────────

@mcp.tool(name="execute_paper_trade", description="Executes a simulated paper trade. Direction must be BUY, SELL, or HOLD.")
def mcp_execute_paper_trade(
    direction: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    confidence_score: float,
    reasoning: str,
    cycle_id: str = "",
) -> str:
    return execute_paper_trade.func(
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        confidence_score=confidence_score,
        reasoning=reasoning,
        cycle_id=cycle_id,
    )


@mcp.tool(name="fetch_trade_performance", description="Fetches closed paper trade logs and performance analytics.")
def mcp_fetch_trade_performance() -> str:
    return fetch_trade_performance.func()


@mcp.tool(name="record_teacher_feedback", description="Records educational feedback or corrective notes on a trade.")
def mcp_record_teacher_feedback(trade_id: str, notes: str) -> str:
    return record_teacher_feedback.func(trade_id=trade_id, notes=notes)


# ─────────────────────────────────────────────
# 6. System Administration Tools
# ─────────────────────────────────────────────

@mcp.tool(name="check_agent_health", description="Checks heartbeats, task counts, and uptime for all 16+ active agents.")
def mcp_check_agent_health() -> str:
    return check_agent_health.func()


@mcp.tool(name="restart_agent_node", description="Restarts a stuck or crashed agent node and resets its error count.")
def mcp_restart_agent_node(agent_name: str) -> str:
    return restart_agent_node.func(agent_name=agent_name)


@mcp.tool(name="send_telegram_notification", description="Transmits warnings, signals, or reports to the Telegram channel.")
def mcp_send_telegram_notification(title: str, message: str, level: str = "info") -> str:
    return send_telegram_notification.func(title=title, message=message, level=level)


@mcp.tool(name="send_telegram_trade_signal", description="Sends a trade signal to Telegram with Approve/Reject inline keyboard buttons.")
def mcp_send_telegram_trade_signal(signal_data: str) -> str:
    return send_telegram_trade_signal.func(signal_data=signal_data)
