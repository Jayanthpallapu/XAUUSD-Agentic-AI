import logging
import asyncio
from typing import List, Dict, Any
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
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

app = FastAPI(
    title="XAUUSD Agentic Company API",
    description="Enterprise Multi-Agent Gold Trading & Observability Dashboard",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class WebSocketLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.loop = asyncio.get_event_loop()

    def emit(self, record):
        log_entry = self.format(record)
        message = {
            "type": "log",
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": log_entry
        }
        if ws_manager.active_connections:
            try:
                asyncio.run_coroutine_threadsafe(ws_manager.broadcast(message), self.loop)
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

@app.on_event("startup")
async def startup_event():
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

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)
