import logging
import json
import requests
from datetime import datetime
from langchain_core.tools import tool
from config import settings
from governance.audit.supabase_client import db_service

logger = logging.getLogger("system_tools")


@tool
def check_agent_health() -> str:
    """
    Checks the status, error count, task count, and accuracy rating
    of all AI agents registered in the system.
    """
    try:
        agents = db_service.select("agent_registry")
        if not agents:
            return "No agents registered in the database."
        reports = []
        for ag in agents:
            name = ag.get("name", "Unknown")
            status = ag.get("status", "unknown")
            errors = ag.get("total_errors", 0)
            tasks = ag.get("total_tasks_completed", 0)
            accuracy = ag.get("accuracy_score", 1.0)
            hb = ag.get("last_heartbeat", "never")
            status_symbol = "🟢" if status == "active" else "🔴" if status == "error" else "🟡"
            reports.append(
                f"{status_symbol} Agent: {name}\n"
                f"   Status: {status.upper()}\n"
                f"   Accuracy Rating: {accuracy * 100:.1f}%\n"
                f"   Tasks Completed: {tasks} | Failures: {errors}\n"
                f"   Last Heartbeat: {hb}"
            )
        return "--- Agent System Health Report ---\n\n" + "\n\n".join(reports)
    except Exception as e:
        logger.error(f"Error checking agent health: {e}")
        return f"Error retrieving agent health: {str(e)}"


@tool
def restart_agent_node(agent_name: str) -> str:
    """
    Restarts a malfunctioning or error-state agent node, resetting its error counts
    and restoring its status to ACTIVE.
    """
    try:
        filters = {"name": agent_name}
        agents = db_service.select("agent_registry", filters)
        if not agents:
            return f"Error: Agent '{agent_name}' is not registered in the system."
        db_service.update(
            "agent_registry",
            filters,
            {"status": "active", "total_errors": 0, "last_heartbeat": datetime.utcnow().isoformat()},
        )
        db_service.insert(
            "audit_log",
            {
                "agent_name": "SupervisorAgent",
                "action": f"RESTART_AGENT_{agent_name}",
                "status": "success",
                "input_data": {"target_agent": agent_name},
                "output_data": {"result": "success"},
                "duration_ms": 12.0,
            },
        )
        return f"🔄 Agent node '{agent_name}' restarted successfully! Errors reset, status set to ACTIVE."
    except Exception as e:
        logger.error(f"Error restarting agent: {e}")
        return f"Error restarting agent: {str(e)}"


@tool
def send_telegram_notification(title: str, message: str, level: str = "info") -> str:
    """
    Sends a formatted alert or report to the supervisor's Telegram channel.
    Levels can be: 'info', 'warning', or 'critical'.
    """
    level = level.lower().strip()
    emoji = "🟢 INFO:" if level == "info" else "🟡 WARNING:" if level == "warning" else "🚨 CRITICAL ALERT:"
    formatted_msg = (
        f"{emoji} {title}\n"
        f"Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
        f"{message}"
    )
    try:
        db_service.insert(
            "notifications",
            {"level": level, "title": title, "message": message, "read": False, "telegram_sent": False},
        )
    except Exception as e:
        logger.error(f"Error saving notification to DB: {e}")

    if settings.is_telegram_configured:
        try:
            url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {"chat_id": settings.TELEGRAM_CHAT_ID, "text": formatted_msg, "parse_mode": "HTML"}
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                return f"Telegram notification sent successfully (Level: {level})."
            return f"Telegram API error: {res.status_code}. Response: {res.text}"
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}")
            return f"Telegram notification failed: {str(e)}"

    logger.info(f"TELEGRAM DEV OUTPUT:\n{formatted_msg}")
    return "Telegram notification printed to local logs (Telegram bot not configured)."


@tool
def send_telegram_trade_signal(signal_data: str) -> str:
    """
    Sends a formatted trade signal to Telegram with an APPROVE / REJECT inline keyboard.
    The signal_data must be a JSON string with keys: signal_id, direction, entry_price,
    stop_loss, take_profit_1, lot_size, risk_reward_ratio, account_risk_pct,
    fundamental_reason, technical_reason, combined_confidence.
    Returns the Telegram message_id of the sent message (needed to update the keyboard later).
    """
    if not settings.is_telegram_configured:
        logger.info(f"TRADE SIGNAL DEV OUTPUT: {signal_data}")
        return "Trade signal printed to local logs (Telegram not configured). message_id: 0"

    try:
        signal = json.loads(signal_data)
        signal_id = signal.get("signal_id", "N/A")
        direction = signal.get("direction", "N/A")
        entry = signal.get("entry_price", 0.0)
        sl = signal.get("stop_loss", 0.0)
        tp1 = signal.get("take_profit_1", 0.0)
        tp2 = signal.get("take_profit_2")
        lot = signal.get("lot_size", 0.01)
        rr = signal.get("risk_reward_ratio", 0.0)
        risk_pct = signal.get("account_risk_pct", 1.0)
        conf = signal.get("combined_confidence", 0.0)
        fund_reason = signal.get("fundamental_reason", "")
        tech_reason = signal.get("technical_reason", "")

        direction_emoji = "📈 BUY" if direction == "BUY" else "📉 SELL"
        tp2_line = f"\n📍 Take Profit 2: ${tp2:.2f}" if tp2 else ""

        msg = (
            f"🚨 <b>NEW TRADE SIGNAL — XAU/USD</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{direction_emoji} <b>{direction}</b>\n\n"
            f"📌 Entry: <b>${entry:.2f}</b>\n"
            f"🛑 Stop Loss: <b>${sl:.2f}</b>\n"
            f"🎯 Take Profit 1: <b>${tp1:.2f}</b>{tp2_line}\n\n"
            f"📊 Risk/Reward: <b>1:{rr:.1f}</b>\n"
            f"🎲 Lot Size: <b>{lot}</b>\n"
            f"💰 Account Risk: <b>{risk_pct:.1f}%</b>\n"
            f"🧠 Confidence: <b>{conf * 100:.0f}%</b>\n\n"
            f"📰 <b>Fundamental:</b>\n{fund_reason[:300]}\n\n"
            f"📐 <b>Technical:</b>\n{tech_reason[:300]}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Signal ID: {signal_id[:8]}</i>\n"
            f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        )

        inline_keyboard = {
            "inline_keyboard": [[
                {"text": "✅ APPROVE TRADE", "callback_data": f"approve:{signal_id}"},
                {"text": "❌ REJECT TRADE", "callback_data": f"reject:{signal_id}"},
            ]]
        }

        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": settings.TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
            "reply_markup": json.dumps(inline_keyboard),
        }
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            result = res.json()
            message_id = result.get("result", {}).get("message_id", 0)
            logger.info(f"Trade signal sent to Telegram. message_id={message_id}")
            return f"Trade signal sent to Telegram successfully. message_id={message_id}"
        return f"Telegram API error {res.status_code}: {res.text}"
    except Exception as e:
        logger.error(f"send_telegram_trade_signal failed: {e}")
        return f"Error sending trade signal to Telegram: {str(e)}"
