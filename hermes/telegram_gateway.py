"""
Hermes Two-Way Telegram Command Gateway
========================================
Full bidirectional Telegram interface for the XAUUSD Agentic Company.
Uses the existing Telegram bot credentials from .env.

Supported Commands:
  /cycle     - Trigger an immediate market analysis cycle
  /positions - Show all currently active paper trade positions
  /status    - Show system status (agent_active, last cycle, memory stats)
  /report    - Show latest performance report (win rate, PnL, etc.)
  /memory    - Show Hermes memory stats (lesson counts per agent)
  /help      - List all available commands

Architecture:
  - Webhook-based: Telegram sends updates to /hermes/telegram endpoint
  - Falls back to getUpdates polling if webhook not registered
  - Uses existing TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from config
"""

import logging
import requests
from datetime import datetime
from typing import Optional, Dict, Any

from config import settings
from governance.audit.supabase_client import db_service
from hermes.memory_store import hermes_memory

logger = logging.getLogger("hermes_telegram")

TELEGRAM_API_BASE = "https://api.telegram.org"


def send_message(
    text: str,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML",
) -> bool:
    """
    Send a message to a Telegram chat using the configured bot.

    Args:
        text: Message text (supports HTML formatting)
        chat_id: Target chat ID (defaults to TELEGRAM_CHAT_ID from env)
        parse_mode: 'HTML' or 'MarkdownV2'

    Returns:
        True if sent successfully, False otherwise
    """
    target_chat = chat_id or settings.TELEGRAM_CHAT_ID
    if not settings.is_telegram_configured or not target_chat:
        logger.warning("Telegram not configured. Message not sent.")
        return False

    try:
        url = f"{TELEGRAM_API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": parse_mode,
        }
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            return True
        else:
            logger.error(f"Telegram send failed [{res.status_code}]: {res.text}")
            return False
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return False


def register_webhook(webhook_url: str) -> bool:
    """
    Register the FastAPI webhook URL with Telegram so updates are pushed automatically.
    Call this once on startup if you have a public HTTPS URL.

    Args:
        webhook_url: Full HTTPS URL to /hermes/telegram endpoint
                     e.g. 'https://your-render-app.onrender.com/hermes/telegram'
    """
    if not settings.is_telegram_configured:
        return False

    try:
        url = f"{TELEGRAM_API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/setWebhook"
        res = requests.post(url, json={"url": webhook_url}, timeout=10)
        data = res.json()
        if data.get("ok"):
            logger.info(f"Telegram webhook registered: {webhook_url}")
            return True
        else:
            logger.warning(f"Telegram webhook registration failed: {data}")
            return False
    except Exception as e:
        logger.error(f"Telegram webhook registration error: {e}")
        return False


def build_status_message(agent_active: bool, active_connections: int) -> str:
    """Build a formatted system status message for Telegram."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    status_icon = "🟢" if agent_active else "🔴"
    mem_stats = hermes_memory.get_stats()
    total_lessons = mem_stats.get("total_lessons", 0)
    lessons_by_agent = mem_stats.get("lessons_by_agent", {})

    lesson_lines = (
        "\n".join([f"  • {name}: {count}" for name, count in lessons_by_agent.items()])
        or "  • No lessons yet"
    )

    return (
        f"<b>🤖 XAUUSD Agentic Company — System Status</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{status_icon} <b>Agent System:</b> {'RUNNING' if agent_active else 'INACTIVE'}\n"
        f"📡 <b>Frontend Connections:</b> {active_connections}\n"
        f"🕒 <b>Timestamp:</b> {now}\n\n"
        f"🧠 <b>Hermes Memory Bank:</b> {total_lessons} total lessons\n"
        f"{lesson_lines}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Use /help to see all available commands."
    )


def build_positions_message() -> str:
    """Build a formatted active positions message for Telegram."""
    try:
        trades = db_service.select("trade_signals", {"status": "active"})
        if not trades:
            return (
                "📊 <b>Active Paper Positions</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "No active positions open currently.\n"
                "Use /cycle to trigger a new analysis."
            )

        lines = ["📊 <b>Active Paper Positions</b>\n━━━━━━━━━━━━━━━━━━━━━━━"]
        for i, t in enumerate(trades, 1):
            direction = t.get("direction", "N/A")
            icon = "🟢" if direction == "BUY" else "🔴"
            lines.append(
                f"\n{icon} <b>Trade {i}: {direction} XAUUSD</b>\n"
                f"  Entry: ${float(t.get('entry_price', 0)):.2f}\n"
                f"  SL: ${float(t.get('stop_loss', 0)):.2f} | TP: ${float(t.get('take_profit', 0)):.2f}\n"
                f"  Confidence: {float(t.get('confidence_score', 0)) * 100:.0f}%\n"
                f"  Opened: {str(t.get('opened_at', 'N/A'))[:16]}"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Error building positions message: {e}")
        return "❌ Error retrieving positions. Please check backend logs."


def build_performance_message() -> str:
    """Build a formatted performance report message for Telegram."""
    try:
        reports = db_service.select("performance_reports")
        if not reports:
            return (
                "📈 <b>Performance Report</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "No performance data available yet.\n"
                "Run a few cycles first to generate statistics."
            )
        latest = max(reports, key=lambda x: x.get("created_at", ""))
        win_rate = latest.get("win_rate", 0.0)
        total_pnl = latest.get("total_pnl", 0.0)
        sharpe = latest.get("sharpe_ratio", 0.0)
        drawdown = latest.get("max_drawdown", 0.0)
        profit_factor = latest.get("profit_factor", 0.0)
        total_trades = latest.get("total_trades", 0)
        wins = latest.get("winning_trades", 0)
        losses = latest.get("losing_trades", 0)

        pnl_icon = "📈" if total_pnl >= 0 else "📉"
        return (
            f"📊 <b>Latest Performance Report</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Net P&L:</b> ${total_pnl:,.2f} USD {pnl_icon}\n"
            f"🏆 <b>Win Rate:</b> {win_rate:.1f}% ({wins}W / {losses}L)\n"
            f"📊 <b>Total Trades:</b> {total_trades}\n"
            f"⚡ <b>Profit Factor:</b> {profit_factor:.2f}\n"
            f"📉 <b>Max Drawdown:</b> {drawdown:.2f}%\n"
            f"📐 <b>Sharpe Ratio:</b> {sharpe:.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Account: $10,000 Paper Trading</i>"
        )
    except Exception as e:
        logger.error(f"Error building performance message: {e}")
        return "❌ Error retrieving performance data."


def build_memory_message() -> str:
    """Build a Hermes memory stats message for Telegram."""
    stats = hermes_memory.get_stats()
    total = stats.get("total_lessons", 0)
    by_agent = stats.get("lessons_by_agent", {})
    total_obs = stats.get("total_observations", 0)

    lines = [
        "🧠 <b>Hermes Memory Bank Stats</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        f"📚 <b>Total Lessons Stored:</b> {total}",
        f"🔭 <b>Cycle Observations:</b> {total_obs}",
        "\n<b>Lessons by Agent:</b>",
    ]
    for agent, count in by_agent.items():
        lines.append(f"  • {agent}: {count} lesson(s)")

    if not by_agent:
        lines.append("  • No lessons recorded yet. Run cycles to build memory.")

    lines.append("\n<i>Memory grows automatically after every cycle.</i>")
    return "\n".join(lines)


HELP_MESSAGE = """
🤖 <b>XAUUSD Agentic Company — Command Reference</b>
━━━━━━━━━━━━━━━━━━━━━━━

<b>System Control:</b>
/status    — View agent system status & memory stats
/cycle     — Trigger an immediate analysis cycle

<b>Trading Intelligence:</b>
/positions — View all active paper trade positions
/report    — View latest performance report (PnL, win rate)

<b>Hermes AI Memory:</b>
/memory    — View Hermes memory bank statistics

/help      — Show this help message

━━━━━━━━━━━━━━━━━━━━━━━
<i>All commands work 24/7. System execution must be ON to run cycles.</i>
"""


async def process_telegram_update(
    update: Dict[str, Any],
    agent_active: bool,
    active_connections: int,
    trigger_cycle_fn,
) -> None:
    """
    Process an incoming Telegram update and route commands to the correct handler.

    Args:
        update: Raw Telegram update dict from webhook
        agent_active: Current agent execution state
        active_connections: Number of active WebSocket connections
        trigger_cycle_fn: Async callable to trigger a market analysis cycle
    """
    try:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip().lower()

        if not chat_id or not text:
            return

        # Security: only respond to configured chat
        allowed_chat = str(settings.TELEGRAM_CHAT_ID)
        if chat_id != allowed_chat:
            logger.warning(
                f"Rejected Telegram update from unauthorized chat: {chat_id}"
            )
            return

        logger.info(f"Telegram command received: '{text}' from chat {chat_id}")

        # Command routing
        if text.startswith("/help"):
            send_message(HELP_MESSAGE, chat_id)

        elif text.startswith("/status"):
            send_message(
                build_status_message(agent_active, active_connections), chat_id
            )

        elif text.startswith("/cycle"):
            if not agent_active:
                send_message(
                    "⚠️ <b>System Execution is OFF.</b>\n"
                    "Turn it ON from the dashboard first, then send /cycle.",
                    chat_id,
                )
            else:
                send_message(
                    "🔄 <b>Analysis cycle triggered!</b>\n"
                    "Running market analysis in background...\n"
                    "You'll receive results shortly via Telegram.",
                    chat_id,
                )
                try:
                    import asyncio

                    asyncio.create_task(trigger_cycle_fn())
                except Exception as e:
                    logger.error(f"Error triggering cycle from Telegram: {e}")
                    send_message(f"❌ Error triggering cycle: {str(e)}", chat_id)

        elif text.startswith("/positions"):
            send_message(build_positions_message(), chat_id)

        elif text.startswith("/report"):
            send_message(build_performance_message(), chat_id)

        elif text.startswith("/memory"):
            send_message(build_memory_message(), chat_id)

        else:
            send_message(
                f"❓ Unknown command: <code>{text}</code>\n"
                "Send /help to see available commands.",
                chat_id,
            )

    except Exception as e:
        logger.error(f"Error processing Telegram update: {e}")
