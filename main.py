import logging
import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import (
    FastAPI,
    BackgroundTasks,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    Request,
    Response,
    Depends,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn
import requests
from config import settings
from governance.audit.supabase_client import db_service
from orchestration.graph import FlowManager

# Hermes Agent imports
from hermes.memory_store import hermes_memory
from hermes.scheduler import hermes_scheduler
from hermes.telegram_gateway import process_telegram_update, register_webhook

# Setup Logger
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("api_server")

# Global Agent execution control state
agent_active = False

# APScheduler: kept as optional fallback but Hermes scheduler is primary
try:
    from apscheduler.schedulers.background import BackgroundScheduler

    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False
    logger.info(
        "APScheduler not installed. Hermes async scheduler is active as primary."
    )

# Optional starlette sse transport for MCP
try:
    from mcp.server.sse import SseServerTransport

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("mcp python package not installed. HTTP MCP endpoints disabled.")


app = FastAPI(
    title="XAUUSD Agentic Company API",
    description="Enterprise Multi-Agent Gold Trading & Observability Dashboard",
    version="1.0.0",
)

# Restrict CORS to the configured frontend URL only (never wildcard in production)
_default_origins = "http://localhost:3000,https://xauusd-agentic-ai.vercel.app,https://xauusd-agentic-ai-6g3p.vercel.app"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("FRONTEND_URL", _default_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# 1. Security Authorization Dependencies (Supabase JWT/OAuth2 Verification)
security_bearer = HTTPBearer(auto_error=False)


async def verify_supabase_jwt(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
):
    """Verifies standard bearer token signature or query token parameter against Supabase Auth API."""
    token = None
    if credentials:
        token = credentials.credentials
    else:
        # Fallback to query parameter (common in browser SSE clients)
        token = request.query_params.get("token")

    if not token:
        # If no credentials exist, allow request in mock/development mode, but log warning.
        # In strict enterprise production mode, raise 401 Unauthorized.
        if not settings.is_supabase_configured:
            logger.info(
                "Anonymous access allowed on MCP endpoint (Development Mode - Supabase offline)."
            )
            return "developer-bypass"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization token.",
        )

    if not settings.is_supabase_configured:
        # Development mode bypass
        logger.info(f"Bypassing JWT validation for token: {token[:8]}...")
        return "developer-bypass"

    # Call Supabase Auth endpoint to verify JWT
    try:
        url = f"{settings.SUPABASE_URL}/auth/v1/user"
        headers = {"Authorization": f"Bearer {token}", "apikey": settings.SUPABASE_KEY}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            user_data = res.json()
            logger.info(
                f"Authenticated user: {user_data.get('email')} via Supabase JWT."
            )
            return user_data
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid Supabase Auth token signature: {res.text}",
            )
    except Exception as e:
        logger.error(f"Supabase Auth server error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication server unavailable.",
        )


# 2. Connection Manager for Websockets Live Streams
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.disconnect_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            f"New WebSocket connection accepted. Total active: {len(self.active_connections)}"
        )
        if self.disconnect_task and not self.disconnect_task.done():
            self.disconnect_task.cancel()
            logger.info("Frontend reconnected. Auto-shutdown timer cancelled.")

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(
            f"WebSocket disconnected. Remaining: {len(self.active_connections)}"
        )

        global agent_active
        if len(self.active_connections) == 0 and agent_active:
            self.start_shutdown_timer()

    def start_shutdown_timer(self):
        if self.disconnect_task and not self.disconnect_task.done():
            self.disconnect_task.cancel()

        async def shutdown_timer():
            try:
                logger.info(
                    "No active connections. Starting 15-minute auto-shutdown countdown..."
                )
                await asyncio.sleep(900)  # 15 minutes
                global agent_active
                if len(self.active_connections) == 0 and agent_active:
                    agent_active = False
                    logger.info(
                        "Auto-shutdown: No frontend connection detected for 15 minutes. Agent stopped."
                    )
                    try:
                        db_service.insert(
                            "audit_log",
                            {
                                "agent_name": "SupervisorAgent",
                                "action": "AUTO_SHUTDOWN",
                                "status": "success",
                                "error_message": "Agent execution automatically stopped due to frontend inactivity (15 mins).",
                            },
                        )
                    except Exception as db_err:
                        logger.error(
                            f"Failed to insert audit log on auto-shutdown: {db_err}"
                        )
            except asyncio.CancelledError:
                logger.info("Auto-shutdown timer cancelled.")
            except Exception as e:
                logger.error(f"Error in auto-shutdown timer: {e}")

        try:
            self.disconnect_task = asyncio.create_task(shutdown_timer())
        except RuntimeError:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self.disconnect_task = loop.create_task(shutdown_timer())
            else:
                logger.warning(
                    "Could not start auto-shutdown timer: no running event loop found."
                )

    async def broadcast(self, message: Dict[str, Any]):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting WebSocket message: {e}")


ws_manager = ConnectionManager()


# 3. Live Logs Streaming Websockets Handler
class WebSocketLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self._loop = None

    def _get_loop(self):
        """Lazily fetch the running event loop to avoid deprecation warnings."""
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    def emit(self, record):
        log_entry = self.format(record)
        message = {
            "type": "log",
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": log_entry,
        }
        if ws_manager.active_connections:
            loop = self._get_loop()
            if loop and loop.is_running():
                try:
                    asyncio.run_coroutine_threadsafe(
                        ws_manager.broadcast(message), loop
                    )
                except Exception:
                    pass


ws_log_handler = WebSocketLogHandler()
ws_log_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
logging.getLogger().addHandler(ws_log_handler)


def run_cycle_background(cycle_id: str = "") -> Dict[str, Any]:
    try:
        asyncio.run(
            ws_manager.broadcast(
                {
                    "type": "status",
                    "event": "cycle_started",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
        )

        results = FlowManager.run_cycle()

        asyncio.run(
            ws_manager.broadcast(
                {
                    "type": "status",
                    "event": "cycle_completed",
                    "timestamp": datetime.utcnow().isoformat(),
                    "results": results,
                }
            )
        )
        return results
    except Exception as e:
        logger.error(f"Error in background cycle: {e}")
        asyncio.run(
            ws_manager.broadcast(
                {
                    "type": "status",
                    "event": "cycle_failed",
                    "timestamp": datetime.utcnow().isoformat(),
                    "error": str(e),
                }
            )
        )
        return {}


def scheduled_job():
    global agent_active
    if not agent_active:
        logger.info("Scheduled cycle skipped: Agent is inactive.")
        return
    now = datetime.utcnow()
    if now.weekday() in [0, 1, 2, 3, 4]:
        logger.info("Executing scheduled XAUUSD analysis cycle...")
        run_cycle_background()
    else:
        logger.info("Skipping scheduled cycle. XAUUSD market is closed (Weekend).")


# 4. Standard Dashboard API Routes
@app.get("/")
def read_root():
    mem_stats = hermes_memory.get_stats()
    return {
        "status": "online",
        "market": "XAUUSD",
        "time_utc": datetime.utcnow().isoformat(),
        "supabase_configured": settings.is_supabase_configured,
        "telegram_configured": settings.is_telegram_configured,
        "hermes_llm": "OpenRouter Hermes 3 405B"
        if settings.OPENROUTER_API_KEY
        else "Groq LLaMA-3.3-70B",
        "hermes_memory_lessons": mem_stats.get("total_lessons", 0),
    }


@app.get("/api/dashboard")
def get_dashboard():
    agents = db_service.select("agent_registry")
    trades = db_service.select("trade_signals")
    cycles = db_service.select("analysis_cycles")
    notifications = db_service.select("notifications")

    correlation = db_service.select("correlation_reports")
    news = db_service.select("gold_news_reports")
    performance = db_service.select("performance_reports")
    supervisor = db_service.select("supervisor_reports")

    latest_correlation = max(
        correlation, key=lambda x: x.get("created_at", ""), default=None
    )
    latest_news = max(news, key=lambda x: x.get("created_at", ""), default=None)
    latest_performance = max(
        performance, key=lambda x: x.get("created_at", ""), default=None
    )
    latest_supervisor = max(
        supervisor, key=lambda x: x.get("created_at", ""), default=None
    )

    active_positions = [t for t in trades if t.get("status") == "active"]
    closed_trades = [
        t for t in trades if t.get("status") in ["closed_win", "closed_loss"]
    ]
    win_rate = 0.0
    total_pnl = 0.0

    if latest_performance:
        win_rate = latest_performance.get("win_rate", 0.0)
        total_pnl = latest_performance.get("total_pnl", 0.0)
    elif closed_trades:
        wins = len([t for t in closed_trades if t.get("status") == "closed_win"])
        win_rate = (wins / len(closed_trades)) * 100.0
        total_pnl = sum(float(t.get("pnl_usd", 0.0) or 0.0) for t in trades)

    confluence_score = 50.0
    if latest_correlation:
        confluence_score = latest_correlation.get("overall_confluence_score", 50.0)

    sorted_notifs = sorted(
        notifications, key=lambda x: x.get("created_at", ""), reverse=True
    )[:10]

    # Fetch real-time gold price for frontend sync
    gold_price = 2645.50  # Fallback mock price
    try:
        from tools.definitions.market_data import fetch_gold_price

        gold_price_str = fetch_gold_price.func()
        import re

        match = re.search(r"\$(\d+(?:\.\d+)?)\s*USD", gold_price_str)
        if match:
            gold_price = float(match.group(1))
    except Exception as e:
        logger.error(f"Failed to fetch gold price for dashboard: {e}")

    return {
        "gold_price": gold_price,
        "agents": agents,
        "metrics": {
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "active_positions_count": len(active_positions),
            "total_cycles_count": len(cycles),
            "confluence_score": confluence_score,
        },
        "active_trades": active_positions,
        "latest_correlation": latest_correlation,
        "latest_news": latest_news,
        "latest_performance": latest_performance,
        "latest_supervisor": latest_supervisor,
        "notifications": sorted_notifs,
    }


@app.get("/api/trades")
def get_trades():
    trades = db_service.select("trade_signals")
    return sorted(trades, key=lambda x: x.get("created_at", ""), reverse=True)


@app.get("/api/news")
def get_news():
    news_reports = db_service.select("gold_news_reports")
    return sorted(news_reports, key=lambda x: x.get("created_at", ""), reverse=True)


@app.get("/api/debug-cycles")
def debug_cycles():
    return db_service.select("analysis_cycles")


@app.get("/api/debug-audit")
def debug_audit():
    return db_service.select("audit_log")


@app.get("/api/agent/status")
def get_agent_status():
    global agent_active
    mem_stats = hermes_memory.get_stats()
    return {
        "agent_active": agent_active,
        "active_connections": len(ws_manager.active_connections),
        "shutdown_timer_running": ws_manager.disconnect_task is not None
        and not ws_manager.disconnect_task.done(),
        "hermes_memory": mem_stats,
        "hermes_llm": "OpenRouter Hermes 3 405B"
        if settings.OPENROUTER_API_KEY
        else "Groq LLaMA-3.3-70B",
    }


@app.get("/api/hermes/memory")
def get_hermes_memory():
    """Returns Hermes persistent memory statistics — lesson counts per agent."""
    stats = hermes_memory.get_stats()
    observations = hermes_memory.get_recent_observations(limit=10)
    return {
        "stats": stats,
        "recent_observations": observations,
    }


@app.get("/api/hermes/lessons/{agent_name}")
def get_agent_lessons(agent_name: str):
    """Returns all stored Hermes lessons for a specific agent."""
    lessons_text = hermes_memory.get_lessons(agent_name, k=20)
    count = hermes_memory.get_lesson_count(agent_name)
    return {
        "agent_name": agent_name,
        "lesson_count": count,
        "lessons_formatted": lessons_text,
    }


@app.post("/api/agent/start")
def start_agent():
    global agent_active
    agent_active = True
    logger.info("Agent execution manually activated.")
    try:
        db_service.insert(
            "audit_log",
            {
                "agent_name": "SupervisorAgent",
                "action": "AGENT_START",
                "status": "success",
                "error_message": "Agent execution manually started from dashboard.",
            },
        )
    except Exception as db_err:
        logger.error(f"Failed to insert audit log on start_agent: {db_err}")
    return {"status": "started", "agent_active": True}


@app.post("/api/agent/stop")
def stop_agent():
    global agent_active
    agent_active = False
    logger.info("Agent execution manually deactivated.")
    try:
        db_service.insert(
            "audit_log",
            {
                "agent_name": "SupervisorAgent",
                "action": "AGENT_STOP",
                "status": "success",
                "error_message": "Agent execution manually stopped from dashboard.",
            },
        )
    except Exception as db_err:
        logger.error(f"Failed to insert audit log on stop_agent: {db_err}")
    return {"status": "stopped", "agent_active": False}


@app.post("/api/trigger-cycle")
def trigger_cycle(background_tasks: BackgroundTasks):
    global agent_active
    if not agent_active:
        raise HTTPException(
            status_code=400,
            detail="Cannot trigger cycle when Agent is inactive. Please start the agent first.",
        )
    background_tasks.add_task(run_cycle_background)
    return {
        "status": "triggered",
        "message": "Manual market analysis cycle dispatched to background task queue.",
    }


@app.post("/api/agents/{name}/restart")
def restart_agent(name: str):
    filters = {"name": name}
    agents = db_service.select("agent_registry", filters)
    if not agents:
        raise HTTPException(status_code=404, detail="Agent registry node not found.")

    db_service.update(
        "agent_registry",
        filters,
        {
            "status": "active",
            "total_errors": 0,
            "last_heartbeat": datetime.utcnow().isoformat(),
        },
    )

    return {
        "status": "success",
        "message": f"Agent node '{name}' manually restarted and errors reset.",
    }


AGENT_STATIC_METADATA = {
    "NewsResearchAgent": {
        "goal": "Research and analyze all gold-relevant news, economic events, Fed communications, inflation data, and geopolitical factors to determine fundamental gold sentiment.",
        "backstory": "Veteran Financial Journalist and Macro Analyst. Monitors breaking geopolitical events, central bank announcements, CPI/PPI releases, FOMC speeches. Hawkish Fed = bearish gold; dovish Fed = bullish gold.",
        "tools": [
            {
                "name": "fetch_gold_price",
                "description": "Fetches real-time Gold spot price.",
            },
            {
                "name": "fetch_news_rss",
                "description": "Google News RSS for gold/forex queries.",
            },
            {
                "name": "analyze_news_sentiment",
                "description": "Alpha Vantage news sentiment scoring.",
            },
            {
                "name": "fetch_economic_calendar",
                "description": "Daily economic calendar events.",
            },
            {
                "name": "scrape_kitco_news",
                "description": "Live Kitco gold news scraper.",
            },
            {
                "name": "scrape_forex_factory_calendar",
                "description": "Forex Factory high-impact events.",
            },
            {
                "name": "fetch_finnhub_news",
                "description": "Finnhub professional market news.",
            },
            {
                "name": "fetch_alpha_vantage_sentiment",
                "description": "Alpha Vantage XAU/USD sentiment scores.",
            },
        ],
    },
    "CorrelationAgent": {
        "goal": "Analyze DXY, US10Y yields, commodities, crypto, and equity indices to determine their combined net impact on Gold (XAUUSD).",
        "backstory": "Senior Quantitative Analyst specializing in macro correlations. DXY rising = bearish gold. US10Y yields rising = bearish gold. VIX spiking = bullish gold. FRED API provides official yield data.",
        "tools": [
            {
                "name": "fetch_forex_prices",
                "description": "DXY, EUR/USD, and key forex pairs.",
            },
            {
                "name": "fetch_commodities_prices",
                "description": "Silver, WTI Oil, Brent, Copper.",
            },
            {
                "name": "fetch_crypto_prices",
                "description": "Bitcoin risk sentiment indicator.",
            },
            {"name": "fetch_market_indices", "description": "S&P500, VIX, DXY."},
            {
                "name": "fetch_treasury_yields",
                "description": "US 10Y and 2Y Treasury yields via FRED.",
            },
        ],
    },
    "FundamentalDirectionAgent": {
        "goal": "Synthesize news research and correlation analysis into BULLISH, BEARISH, or NEUTRAL direction with confidence score.",
        "backstory": "Chief Fundamental Analyst. Weighs news sentiment vs correlation evidence. If both agree: high confidence. If they disagree: NEUTRAL. High-impact events override everything.",
        "tools": [],
    },
    "TechnicalDirectionAgent": {
        "goal": "Synthesize all 6 timeframe analyses into final technical directional bias with entry zone and invalidation level.",
        "backstory": "Head Technical Analyst. Higher timeframe trumps lower. 1W/1D = macro. 4H/1H = swing. 15M/5M = entry. Uses ICT concepts: order blocks, FVG, liquidity pools, market structure.",
        "tools": [
            {
                "name": "fetch_gold_price",
                "description": "Fetches current gold spot price for entry context.",
            }
        ],
    },
    "Analyst_1W": {
        "goal": "Analyze XAU/USD 1-Week timeframe technical structure.",
        "backstory": "1-Week specialist. Identifies macro trend, weekly OBs, and major S/R zones.",
        "tools": [
            {
                "name": "fetch_ohlcv_data",
                "description": "Fetches 1W OHLCV from Twelve Data.",
            },
            {
                "name": "analyze_price_structure",
                "description": "Analyzes 1W price structure.",
            },
        ],
    },
    "Analyst_1D": {
        "goal": "Analyze XAU/USD 1-Day timeframe technical structure.",
        "backstory": "1-Day specialist. Identifies daily trend, daily OBs, and key daily levels.",
        "tools": [
            {
                "name": "fetch_ohlcv_data",
                "description": "Fetches 1D OHLCV from Twelve Data.",
            },
            {
                "name": "analyze_price_structure",
                "description": "Analyzes 1D price structure.",
            },
        ],
    },
    "Analyst_4H": {
        "goal": "Analyze XAU/USD 4-Hour timeframe technical structure.",
        "backstory": "4H specialist. Identifies intermediate swing structure, 4H OBs, BOS/CHoCH signals.",
        "tools": [
            {
                "name": "fetch_ohlcv_data",
                "description": "Fetches 4H OHLCV from Twelve Data.",
            },
            {
                "name": "analyze_price_structure",
                "description": "Analyzes 4H price structure.",
            },
        ],
    },
    "Analyst_1H": {
        "goal": "Analyze XAU/USD 1-Hour timeframe technical structure.",
        "backstory": "1H specialist. Identifies 1H swing structure, liquidity sweeps, and fair value gaps.",
        "tools": [
            {
                "name": "fetch_ohlcv_data",
                "description": "Fetches 1H OHLCV from Twelve Data.",
            },
            {
                "name": "analyze_price_structure",
                "description": "Analyzes 1H price structure.",
            },
        ],
    },
    "Analyst_15M": {
        "goal": "Analyze XAU/USD 15-Minute timeframe for entry trigger confirmation.",
        "backstory": "15M specialist. Identifies precise entry triggers: engulfing candles, pin bars, BOS on LTF.",
        "tools": [
            {
                "name": "fetch_ohlcv_data",
                "description": "Fetches 15M OHLCV from Twelve Data.",
            },
            {
                "name": "analyze_price_structure",
                "description": "Analyzes 15M price structure.",
            },
        ],
    },
    "Analyst_5M": {
        "goal": "Analyze XAU/USD 5-Minute timeframe for precision entry timing.",
        "backstory": "5M specialist. Provides the most granular entry timing confirmation within the LTF structure.",
        "tools": [
            {
                "name": "fetch_ohlcv_data",
                "description": "Fetches 5M OHLCV from Twelve Data.",
            },
            {
                "name": "analyze_price_structure",
                "description": "Analyzes 5M price structure.",
            },
        ],
    },
    "QATradeAgent": {
        "goal": "Validate trade confluence, enforce RR >= 1:3, calculate lot size, and produce APPROVED or REJECTED decision.",
        "backstory": "Chief Risk Manager. Capital protection is the top priority. Enforces strict rules: confluence required, RR >= 1:3, max 1% account risk. No exceptions.",
        "tools": [
            {
                "name": "fetch_gold_price",
                "description": "Current gold price for entry validation.",
            }
        ],
    },
    "TelegramReportAgent": {
        "goal": "Send approved trade signals to Telegram with inline Approve/Reject keyboard. Awaits human decision.",
        "backstory": "Human-in-the-loop gatekeeper. Sends rich formatted trade card to Telegram with inline keyboard. Stores signal as pending_approval until user responds.",
        "tools": [
            {
                "name": "send_telegram_trade_signal",
                "description": "Sends trade signal with inline keyboard to Telegram.",
            },
            {
                "name": "send_telegram_notification",
                "description": "Sends general notifications to Telegram.",
            },
        ],
    },
    "TradeExecutionAgent": {
        "goal": "Execute approved paper trades when user clicks Approve in Telegram. Lock the trade journal entry immediately.",
        "backstory": "Paper Trade Executor. Triggered only by Telegram callback after human approval. Creates an immutable trade journal entry. No agent can modify trades after execution.",
        "tools": [
            {
                "name": "execute_paper_trade",
                "description": "Executes paper trade to Supabase trade_signals table.",
            }
        ],
    },
    "TradeJournalAgent": {
        "goal": "Write and maintain the immutable trade journal. Each executed trade is locked with locked=True.",
        "backstory": "Immutable Trade Historian. Writes the final trade record to the trade_journal table with locked=True flag. Only PerformanceAgent may read (never write) these records.",
        "tools": [],
    },
    "PerformanceAgent": {
        "goal": "Observe closed trade results, calculate win rate, PnL, RR achieved, and run attribution analysis.",
        "backstory": "Trading Desk Performance Controller. Reads closed trade journal entries. Calculates metrics: win rate, drawdown, profit factor, attribution per fundamental vs technical factor. Read-only access to trade journal.",
        "tools": [
            {
                "name": "fetch_trade_performance",
                "description": "Fetches paper trading stats from trade_signals table.",
            }
        ],
    },
    "LearningAgent": {
        "goal": "Analyze performance data and propose strategy improvements as recommendations. RECOMMENDATION MODE ONLY — no direct changes.",
        "backstory": "Strategy Improvement Researcher. Analyzes wins vs losses to find patterns. Proposes changes (e.g., 'increase minimum RR to 1:4 for Monday trades'). QATradeAgent must review and approve any recommendation before adoption.",
        "tools": [
            {
                "name": "fetch_trade_performance",
                "description": "Reads performance data for pattern analysis.",
            }
        ],
    },
    "SupervisorAgent": {
        "goal": "Monitor all 16 agents, diagnose errors, restart failed nodes, and send daily summary to Telegram.",
        "backstory": "Chief AI Supervisor. Monitors heartbeats and error counts of all agents. Restarts stuck nodes. Compiles daily execution report. Publishes notifications to Telegram.",
        "tools": [
            {
                "name": "check_agent_health",
                "description": "Checks heartbeats and error counts of all agents.",
            },
            {
                "name": "restart_agent_node",
                "description": "Restarts a failed agent node.",
            },
            {
                "name": "record_teacher_feedback",
                "description": "Records corrective feedback on trades.",
            },
            {
                "name": "fetch_trade_performance",
                "description": "Fetches paper trading stats.",
            },
            {
                "name": "send_telegram_notification",
                "description": "Sends daily summary to Telegram.",
            },
        ],
    },
}


@app.get("/api/agents/{name}")
def get_agent_details(name: str):
    filters = {"name": name}
    agents = db_service.select("agent_registry", filters)
    if not agents:
        raise HTTPException(status_code=404, detail="Agent registry node not found.")

    agent = agents[0]
    metadata = AGENT_STATIC_METADATA.get(
        name, {"goal": "", "backstory": "", "tools": []}
    )

    # Query latest audit logs for this agent
    all_logs = db_service.select("audit_log")
    agent_logs = [log for log in all_logs if log.get("agent_name") == name]
    # Sort by created_at desc and take latest 10
    agent_logs = sorted(
        agent_logs, key=lambda x: x.get("created_at", ""), reverse=True
    )[:10]

    # Combine data
    response_data = {
        "id": agent.get("id"),
        "name": agent.get("name"),
        "role": agent.get("role"),
        "status": agent.get("status"),
        "last_heartbeat": agent.get("last_heartbeat"),
        "avg_response_time_ms": agent.get("avg_response_time_ms"),
        "accuracy_score": agent.get("accuracy_score"),
        "total_tasks_completed": agent.get("total_tasks_completed"),
        "total_errors": agent.get("total_errors"),
        "lessons_learned": agent.get("lessons_learned", []),
        "goal": metadata["goal"],
        "backstory": metadata["backstory"],
        "tools": metadata["tools"],
        "audit_logs": agent_logs,
    }

    return response_data


# ─────────────────────────────────────────────
# New Pipeline API Routes
# ─────────────────────────────────────────────


@app.get("/api/pipeline/signals/pending")
def get_pending_signals():
    """Returns all signals currently pending Telegram approval."""
    signals = db_service.select("pending_signals", {"status": "pending_approval"})
    return sorted(signals, key=lambda x: x.get("created_at", ""), reverse=True)


@app.get("/api/pipeline/signals")
def get_all_signals():
    """Returns all trade signals (pending, approved, rejected, executed)."""
    signals = db_service.select("pending_signals")
    return sorted(signals, key=lambda x: x.get("created_at", ""), reverse=True)


@app.get("/api/pipeline/journal")
def get_trade_journal():
    """Returns all locked trade journal entries."""
    journal = db_service.select("trade_journal")
    return sorted(journal, key=lambda x: x.get("created_at", ""), reverse=True)


@app.get("/api/pipeline/fundamental")
def get_fundamental_reports():
    """Returns the latest fundamental research reports."""
    reports = db_service.select("fundamental_reports")
    return sorted(reports, key=lambda x: x.get("created_at", ""), reverse=True)[:10]


@app.get("/api/pipeline/technical")
def get_technical_reports():
    """Returns the latest technical research reports."""
    reports = db_service.select("technical_reports")
    return sorted(reports, key=lambda x: x.get("created_at", ""), reverse=True)[:10]


@app.get("/api/pipeline/qa")
def get_qa_decisions():
    """Returns the latest QA trade decisions."""
    decisions = db_service.select("qa_decisions")
    return sorted(decisions, key=lambda x: x.get("created_at", ""), reverse=True)[:10]


@app.get("/api/pipeline/learning")
def get_learning_recommendations():
    """Returns all learning agent recommendations. adopted=false means pending QA review."""
    recommendations = db_service.select("learning_recommendations")
    return sorted(recommendations, key=lambda x: x.get("created_at", ""), reverse=True)


@app.post("/api/pipeline/learning/{rec_id}/adopt")
def adopt_learning_recommendation(rec_id: str):
    """Marks a learning recommendation as adopted by QA. QA decision only — not auto-applied."""
    from datetime import datetime

    recommendations = db_service.select("learning_recommendations")
    rec = next((r for r in recommendations if r.get("id") == rec_id), None)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found.")
    db_service.update(
        "learning_recommendations",
        {"id": rec_id},
        {"adopted": True, "adopted_at": datetime.utcnow().isoformat()},
    )
    return {"status": "adopted", "recommendation_id": rec_id}


@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket exception: {e}")
        await ws_manager.disconnect(websocket)


# 5a. Hermes Telegram Webhook Endpoint (Two-Way Command Interface)
@app.post("/hermes/telegram")
async def hermes_telegram_webhook(request: Request):
    """
    Receives Telegram bot updates via webhook.
    Routes commands (/cycle, /positions, /status, /report, /memory, /help)
    to the appropriate handler using the existing TELEGRAM_BOT_TOKEN.

    Setup: Register webhook once by calling:
      POST /hermes/telegram/register?webhook_url=https://your-domain.com/hermes/telegram
    """
    global agent_active
    try:
        update = await request.json()

        # ── Inline Keyboard Callback (Trade Approval / Rejection)
        if "callback_query" in update:
            callback = update["callback_query"]
            callback_data = callback.get("data", "")
            callback_id = callback.get("id", "")
            message = callback.get("message", {})
            chat_id = message.get("chat", {}).get("id", settings.TELEGRAM_CHAT_ID)
            message_id = message.get("message_id")

            # Answer callback query to stop the loading spinner in Telegram UI
            try:
                requests.post(
                    f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                    json={"callback_query_id": callback_id, "text": "Processing..."},
                    timeout=5,
                )
            except Exception:
                pass

            if ":" in callback_data:
                action, signal_id = callback_data.split(":", 1)
                if action in ["approve", "reject"]:
                    from agents.orchestrator.agent import process_telegram_approval

                    result = process_telegram_approval(signal_id, action)

                    # Update the Telegram message to remove inline keyboard
                    action_text = (
                        "APPROVED ✅" if action == "approve" else "REJECTED ❌"
                    )
                    try:
                        requests.post(
                            f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageReplyMarkup",
                            json={
                                "chat_id": chat_id,
                                "message_id": message_id,
                                "reply_markup": json.dumps({"inline_keyboard": []}),
                            },
                            timeout=5,
                        )
                        requests.post(
                            f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": chat_id,
                                "text": f"Signal {signal_id[:8]}: {action_text}",
                                "parse_mode": "HTML",
                            },
                            timeout=5,
                        )
                    except Exception as te:
                        logger.error(f"Telegram callback response error: {te}")

                    return {"ok": True, "result": result}

        # ── Regular text commands
        await process_telegram_update(
            update=update,
            agent_active=agent_active,
            active_connections=len(ws_manager.active_connections),
            trigger_cycle_fn=_async_trigger_cycle,
        )
        return {"ok": True}
    except Exception as e:
        logger.error(f"Hermes Telegram webhook error: {e}")
        return {"ok": False, "error": str(e)}


@app.post("/hermes/telegram/register")
def hermes_telegram_register(webhook_url: str):
    """
    Register the Telegram webhook URL with the Telegram Bot API.
    Call this once after deploying to production with your Render URL:
      POST /hermes/telegram/register?webhook_url=https://your-app.onrender.com/hermes/telegram
    """
    success = register_webhook(webhook_url)
    if success:
        return {"status": "success", "webhook_url": webhook_url}
    return {
        "status": "failed",
        "message": "Check TELEGRAM_BOT_TOKEN in environment variables.",
    }


async def _async_trigger_cycle():
    """Async wrapper to trigger a cycle from Telegram command."""
    global agent_active
    if agent_active:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_cycle_background)


if MCP_AVAILABLE:
    mcp_sse = SseServerTransport("/mcp/messages")

    @app.get("/mcp/sse", dependencies=[Depends(verify_supabase_jwt)])
    async def handle_mcp_sse(request: Request):
        """HTTP event stream connection endpoint for MCP clients."""
        logger.info("Initializing MCP SSE connection session...")
        from tools.registry import mcp

        async with mcp_sse.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            # Access underlying low-level Server instance inside FastMCP
            await mcp._mcp_server.run(
                read_stream,
                write_stream,
                mcp._mcp_server.create_initialization_options(),
            )
        return Response()

    @app.post("/mcp/messages", dependencies=[Depends(verify_supabase_jwt)])
    async def handle_mcp_messages(request: Request):
        """JSON-RPC message transport endpoint for MCP client writes."""
        await mcp_sse.handle_post_message(request.scope, request.receive, request._send)


# 6. Service Lifecycles (lifespan replaces deprecated @app.on_event)
@asynccontextmanager
async def lifespan(app):
    # ====== STARTUP ======
    logger.info("Starting XAUUSD Agentic Company API (Hermes-Enhanced)...")

    # Start Hermes async scheduler (morning briefing at 9 AM UTC Mon-Fri)
    hermes_scheduler.start(morning_briefing_fn=FlowManager.run_morning_briefing)

    # Seed Hermes memory with foundational lessons if memory is empty
    total_lessons = hermes_memory.get_lesson_count()
    if total_lessons == 0:
        logger.info("Hermes Memory Bank is empty. Seeding foundational lessons...")
        try:
            FlowManager.backfill_lessons(days=15)
        except Exception as e:
            logger.warning(f"Non-critical: Could not seed Hermes memory: {e}")
    else:
        logger.info(f"Hermes Memory Bank loaded: {total_lessons} lessons available.")

    # APScheduler as optional fallback for interval-based scheduling
    scheduler = None
    if SCHEDULER_AVAILABLE:
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            scheduled_job,
            "interval",
            minutes=settings.RUN_INTERVAL_MINUTES,
            id="market_analysis_cycle",
        )
        scheduler.start()
        logger.info(
            f"APScheduler (fallback) initialized: every {settings.RUN_INTERVAL_MINUTES} min."
        )

    yield

    # ====== SHUTDOWN ======
    hermes_scheduler.stop()
    logger.info("Hermes scheduler stopped.")

    if SCHEDULER_AVAILABLE and scheduler:
        try:
            scheduler.shutdown(wait=False)
            logger.info("APScheduler shut down successfully.")
        except Exception as e:
            logger.warning(f"Error shutting down APScheduler: {e}")


app.router.lifespan_context = lifespan

# 7. Subprocess standard I/O launch options (for Cursor / Claude Desktop configs)
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--mcp":
        logger.info("Launching Toolset as local Stdin/Stdout MCP Server Subprocess...")
        from tools.registry import mcp

        mcp.run()
        sys.exit(0)

    # Production: do NOT use reload=True — it is a dev-only flag
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT)
