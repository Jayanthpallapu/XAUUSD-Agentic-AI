import logging
import asyncio
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
        "hermes_llm": "OpenRouter Hermes 3 405B" if settings.OPENROUTER_API_KEY else "Groq LLaMA-3.3-70B",
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

    return {
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
        "hermes_llm": "OpenRouter Hermes 3 405B" if settings.OPENROUTER_API_KEY else "Groq LLaMA-3.3-70B",
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
    return {"status": "failed", "message": "Check TELEGRAM_BOT_TOKEN in environment variables."}


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
    hermes_scheduler.start(
        morning_briefing_fn=FlowManager.run_morning_briefing
    )

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
