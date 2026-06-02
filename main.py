import logging
import asyncio
import os
import sys
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect, HTTPException, Request, Response, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn
import requests
from config import settings
from governance.audit.supabase_client import db_service
from orchestration.graph import FlowManager

# Setup Logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("api_server")

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False
    logger.warning("APScheduler package not installed. Scheduled task execution disabled.")

# Optional starlette sse transport for MCP
try:
    from mcp.server.sse import SseServerTransport
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("mcp python package not installed. HTTP MCP endpoints disabled.")

from contextlib import asynccontextmanager

app = FastAPI(
    title="XAUUSD Agentic Company API",
    description="Enterprise Multi-Agent Gold Trading & Observability Dashboard",
    version="1.0.0"
)

# Restrict CORS to the configured frontend URL only (never wildcard in production)
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("FRONTEND_URL", "http://localhost:3000").split(",")
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

async def verify_supabase_jwt(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)):
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
            logger.info("Anonymous access allowed on MCP endpoint (Development Mode - Supabase offline).")
            return "developer-bypass"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization token."
        )

    if not settings.is_supabase_configured:
        # Development mode bypass
        logger.info(f"Bypassing JWT validation for token: {token[:8]}...")
        return "developer-bypass"

    # Call Supabase Auth endpoint to verify JWT
    try:
        url = f"{settings.SUPABASE_URL}/auth/v1/user"
        headers = {
            "Authorization": f"Bearer {token}",
            "apikey": settings.SUPABASE_KEY
        }
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            user_data = res.json()
            logger.info(f"Authenticated user: {user_data.get('email')} via Supabase JWT.")
            return user_data
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid Supabase Auth token signature: {res.text}"
            )
    except Exception as e:
        logger.error(f"Supabase Auth server error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication server unavailable."
        )

# 2. Connection Manager for Websockets Live Streams
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New WebSocket connection accepted. Total active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Remaining: {len(self.active_connections)}")

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
            "message": log_entry
        }
        if ws_manager.active_connections:
            loop = self._get_loop()
            if loop and loop.is_running():
                try:
                    asyncio.run_coroutine_threadsafe(ws_manager.broadcast(message), loop)
                except Exception:
                    pass

ws_log_handler = WebSocketLogHandler()
ws_log_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
logging.getLogger().addHandler(ws_log_handler)

def run_cycle_background(cycle_id: str = "") -> Dict[str, Any]:
    try:
        asyncio.run(ws_manager.broadcast({
            "type": "status",
            "event": "cycle_started",
            "timestamp": datetime.utcnow().isoformat()
        }))
        
        results = FlowManager.run_cycle()
        
        asyncio.run(ws_manager.broadcast({
            "type": "status",
            "event": "cycle_completed",
            "timestamp": datetime.utcnow().isoformat(),
            "results": results
        }))
        return results
    except Exception as e:
        logger.error(f"Error in background cycle: {e}")
        asyncio.run(ws_manager.broadcast({
            "type": "status",
            "event": "cycle_failed",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }))
        return {}

def scheduled_job():
    now = datetime.utcnow()
    if now.weekday() in [0, 1, 2, 3, 4]:
        logger.info("Executing scheduled XAUUSD analysis cycle...")
        run_cycle_background()
    else:
        logger.info("Skipping scheduled cycle. XAUUSD market is closed (Weekend).")

# 4. Standard Dashboard API Routes
@app.get("/")
def read_root():
    return {
        "status": "online",
        "market": "XAUUSD",
        "time_utc": datetime.utcnow().isoformat(),
        "supabase_configured": settings.is_supabase_configured,
        "telegram_configured": settings.is_telegram_configured
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

    latest_correlation = max(correlation, key=lambda x: x.get("created_at", ""), default=None)
    latest_news = max(news, key=lambda x: x.get("created_at", ""), default=None)
    latest_performance = max(performance, key=lambda x: x.get("created_at", ""), default=None)
    latest_supervisor = max(supervisor, key=lambda x: x.get("created_at", ""), default=None)

    active_positions = [t for t in trades if t.get("status") == "active"]
    closed_trades = [t for t in trades if t.get("status") in ["closed_win", "closed_loss"]]
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

    sorted_notifs = sorted(notifications, key=lambda x: x.get("created_at", ""), reverse=True)[:10]

    return {
        "agents": agents,
        "metrics": {
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "active_positions_count": len(active_positions),
            "total_cycles_count": len(cycles),
            "confluence_score": confluence_score
        },
        "active_trades": active_positions,
        "latest_correlation": latest_correlation,
        "latest_news": latest_news,
        "latest_performance": latest_performance,
        "latest_supervisor": latest_supervisor,
        "notifications": sorted_notifs
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


@app.post("/api/trigger-cycle")
def trigger_cycle(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_cycle_background)
    return {
        "status": "triggered",
        "message": "Manual market analysis cycle dispatched to background task queue."
    }

@app.post("/api/agents/{name}/restart")
def restart_agent(name: str):
    filters = {"name": name}
    agents = db_service.select("agent_registry", filters)
    if not agents:
        raise HTTPException(status_code=404, detail="Agent registry node not found.")
        
    db_service.update("agent_registry", filters, {
        "status": "active",
        "total_errors": 0,
        "last_heartbeat": datetime.utcnow().isoformat()
    })
    
    return {
        "status": "success",
        "message": f"Agent node '{name}' manually restarted and errors reset."
    }

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket exception: {e}")
        ws_manager.disconnect(websocket)

# 5. Model Context Protocol (MCP) Server SSE Transport Endpoints
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
                mcp._mcp_server.create_initialization_options()
            )
        return Response()

    @app.post("/mcp/messages", dependencies=[Depends(verify_supabase_jwt)])
    async def handle_mcp_messages(request: Request):
        """JSON-RPC message transport endpoint for MCP client writes."""
        await mcp_sse.handle_post_message(request.scope, request.receive, request._send)

# 6. Service Lifecycles (lifespan replaces deprecated @app.on_event)
@asynccontextmanager
async def lifespan(app):
    # Startup
    if SCHEDULER_AVAILABLE:
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            scheduled_job,
            "interval",
            minutes=settings.RUN_INTERVAL_MINUTES,
            id="market_analysis_cycle"
        )
        scheduler.start()
        logger.info(f"APScheduler initialized. Configured to run every {settings.RUN_INTERVAL_MINUTES} minutes (Monday to Friday only).")
    yield
    # Shutdown (add cleanup here if needed)

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
