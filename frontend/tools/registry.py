import logging
from fastmcp import FastMCP
from mcp import types

# Import tools using absolute project imports
from tools.definitions.market_data import (
    fetch_gold_price,
    fetch_forex_prices,
    fetch_commodities_prices,
    fetch_crypto_prices,
    fetch_market_indices,
    fetch_treasury_yields
)
from tools.definitions.news_calendar import (
    fetch_news_rss,
    analyze_news_sentiment,
    fetch_economic_calendar
)
from tools.definitions.trading_performance import (
    execute_paper_trade,
    fetch_trade_performance,
    record_teacher_feedback
)
from tools.definitions.system import (
    check_agent_health,
    restart_agent_node,
    send_telegram_notification
)

logger = logging.getLogger("mcp_registry")

# Initialize FastMCP Server
mcp = FastMCP("XAUUSD Agentic Company Toolset")

# 1. Market Data Tools
@mcp.tool(name="fetch_gold_price", description="Fetches the current spot price of Gold (XAUUSD) in USD.")
def mcp_fetch_gold_price() -> str:
    return fetch_gold_price()

@mcp.tool(name="fetch_forex_prices", description="Fetches exchange rates for currency pairs. Input format 'EURUSD,USDJPY'.")
def mcp_fetch_forex_prices(pairs: str = "EURUSD,USDJPY,GBPUSD,USDCHF,AUDUSD") -> str:
    return fetch_forex_prices(pairs=pairs)

@mcp.tool(name="fetch_commodities_prices", description="Fetches prices of commodities: Silver, WTI Crude Oil, Brent, Copper.")
def mcp_fetch_commodities_prices() -> str:
    return fetch_commodities_prices()

@mcp.tool(name="fetch_crypto_prices", description="Fetches the current spot price of Bitcoin (BTC) in USD.")
def mcp_fetch_crypto_prices() -> str:
    return fetch_crypto_prices()

@mcp.tool(name="fetch_market_indices", description="Fetches global indices values: US Dollar Index (DXY), S&P 500, VIX.")
def mcp_fetch_market_indices() -> str:
    return fetch_market_indices()

@mcp.tool(name="fetch_treasury_yields", description="Fetches the current US 10-Year Treasury Yield.")
def mcp_fetch_treasury_yields() -> str:
    return fetch_treasury_yields()

# 2. News & Economic Calendar Tools
@mcp.tool(name="fetch_news_rss", description="Fetches latest financial RSS news feed. Query can be 'gold FOMC calendar'.")
def mcp_fetch_news_rss(query: str = "gold price XAUUSD forex") -> str:
    return fetch_news_rss(query=query)

@mcp.tool(name="analyze_news_sentiment", description="Retrieves overall gold news sentiment stats and headlines.")
def mcp_analyze_news_sentiment() -> str:
    return analyze_news_sentiment()

@mcp.tool(name="fetch_economic_calendar", description="Retrieves economic calendars highlighting NFP, FOMC, CPI events.")
def mcp_fetch_economic_calendar() -> str:
    return fetch_economic_calendar()

# 3. Trading Executions Tools
@mcp.tool(name="execute_paper_trade", description="Executes simulated paper trade signals. Direction must be BUY, SELL or HOLD.")
def mcp_execute_paper_trade(
    direction: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    confidence_score: float,
    reasoning: str,
    cycle_id: str = ""
) -> str:
    return execute_paper_trade(
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        confidence_score=confidence_score,
        reasoning=reasoning,
        cycle_id=cycle_id
    )

@mcp.tool(name="fetch_trade_performance", description="Fetches closed simulated trades logs and performance analytics statistics.")
def mcp_fetch_trade_performance() -> str:
    return fetch_trade_performance()

@mcp.tool(name="record_teacher_feedback", description="Records educational feedback or corrective guidelines on a trade.")
def mcp_record_teacher_feedback(trade_id: str, notes: str) -> str:
    return record_teacher_feedback(trade_id=trade_id, notes=notes)

# 4. System Administration Tools
@mcp.tool(name="check_agent_health", description="Checks heartbeats, task counts, and uptime for all active agents.")
def mcp_check_agent_health() -> str:
    return check_agent_health()

@mcp.tool(name="restart_agent_node", description="Restarts stuck or crashed agent nodes and resets error counts.")
def mcp_restart_agent_node(agent_name: str) -> str:
    return restart_agent_node(agent_name=agent_name)

@mcp.tool(name="send_telegram_notification", description="Transmits warnings, signals or reports to Telegram.")
def mcp_send_telegram_notification(title: str, message: str, level: str = "info") -> str:
    return send_telegram_notification(title=title, message=message, level=level)
