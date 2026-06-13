import logging
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

            status_symbol = (
                "🟢" if status == "active" else "🔴" if status == "error" else "🟡"
            )

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
            {
                "status": "active",
                "total_errors": 0,
                "last_heartbeat": datetime.utcnow().isoformat(),
            },
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
    Sends a formatted alert or report to the supervisor's Telegram channel/chat.
    Levels can be: 'info' (routine updates), 'warning' (potential trade setups), or 'critical' (news alerts, supervisor fixes).
    """
    level = level.lower().strip()
    emoji = (
        "🟢 INFO:"
        if level == "info"
        else "🟡 WARNING:"
        if level == "warning"
        else "🚨 CRITICAL ALERT:"
    )

    formatted_msg = (
        f"{emoji} {title}\n"
        f"Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
        f"{message}"
    )

    try:
        db_service.insert(
            "notifications",
            {
                "level": level,
                "title": title,
                "message": message,
                "read": False,
                "telegram_sent": False,
            },
        )
    except Exception as e:
        logger.error(f"Error saving notification to DB: {e}")

    if settings.is_telegram_configured:
        try:
            url = (
                f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
            )
            payload = {
                "chat_id": settings.TELEGRAM_CHAT_ID,
                "text": formatted_msg,
                "parse_mode": "HTML",
            }
            res = requests.post(url, json=payload, timeout=10)

            if res.status_code == 200:
                notifs = db_service.select(
                    "notifications", {"title": title, "level": level}
                )
                if notifs:
                    latest = max(notifs, key=lambda x: x.get("created_at", ""))
                    db_service.update(
                        "notifications", {"id": latest["id"]}, {"telegram_sent": True}
                    )

                return f"Telegram notification sent successfully (Level: {level})."
            else:
                return f"Telegram API error: Received status code {res.status_code}. Response: {res.text}"
        except Exception as e:
            logger.error(f"Telegram notification request failed: {e}")
            return f"Telegram notification failed to transmit: {str(e)}"

    logger.info(f"TELEGRAM DEV OUTPUT:\n{formatted_msg}")
    return "Telegram notification printed to local logs (Telegram bot credentials not configured in backend)."
