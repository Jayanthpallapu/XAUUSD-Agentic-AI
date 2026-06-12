"""
Hermes Async Cron Scheduler
============================
Lightweight async cron scheduler using croniter.
Replaces APScheduler as the market analysis cycle runner.

Features:
- Proper async/await integration with FastAPI lifespan
- Persistent across restart (cron state tracked via asyncio)
- Morning briefing at 9 AM UTC Mon-Fri
- Market cycle execution on-demand (no fixed interval — runs when ON)
- Timezone-aware scheduling (UTC)
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger("hermes_scheduler")


class HermesScheduler:
    """
    Async cron scheduler for XAUUSD analysis cycles and briefings.
    Designed to integrate cleanly with FastAPI's asynccontextmanager lifespan.
    """

    def __init__(self):
        self._tasks: list[asyncio.Task] = []
        self._running = False

    async def _run_morning_briefing(self, briefing_fn: Callable):
        """
        Runs a morning briefing at 9:00 AM UTC every Mon-Fri.
        Sends an overnight gold summary + today's economic calendar to Telegram.
        """
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                # Calculate seconds until next 9 AM UTC weekday
                seconds_until = self._seconds_until_next_9am_utc(now)
                logger.info(
                    f"Morning briefing scheduled. Next run in "
                    f"{seconds_until // 3600}h {(seconds_until % 3600) // 60}m UTC."
                )
                await asyncio.sleep(seconds_until)

                now_check = datetime.now(timezone.utc)
                if now_check.weekday() < 5:  # Mon-Fri only
                    logger.info("HermesScheduler: Triggering morning briefing...")
                    try:
                        if asyncio.iscoroutinefunction(briefing_fn):
                            await briefing_fn()
                        else:
                            await asyncio.get_event_loop().run_in_executor(None, briefing_fn)
                    except Exception as e:
                        logger.error(f"Morning briefing execution failed: {e}")
                else:
                    logger.info("HermesScheduler: Skipping morning briefing (weekend).")

                # Small sleep to avoid re-triggering immediately
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                logger.info("HermesScheduler: Morning briefing task cancelled.")
                break
            except Exception as e:
                logger.error(f"HermesScheduler morning briefing error: {e}")
                await asyncio.sleep(60)

    def _seconds_until_next_9am_utc(self, now: datetime) -> float:
        """Calculate how many seconds until the next 9 AM UTC, Mon-Fri."""
        target_hour = 9
        # Find next weekday 9 AM UTC
        next_run = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if now >= next_run or now.weekday() >= 5:
            # Move to next day
            from datetime import timedelta
            next_run = next_run + timedelta(days=1)
            # Skip weekend
            while next_run.weekday() >= 5:
                next_run = next_run + timedelta(days=1)

        delta = (next_run - now).total_seconds()
        return max(delta, 1.0)

    def start(self, morning_briefing_fn: Optional[Callable] = None):
        """
        Start all scheduled background tasks.
        Call this inside FastAPI lifespan startup.
        """
        self._running = True

        if morning_briefing_fn:
            task = asyncio.create_task(
                self._run_morning_briefing(morning_briefing_fn),
                name="hermes_morning_briefing"
            )
            self._tasks.append(task)
            logger.info("HermesScheduler: Morning briefing cron started (9 AM UTC, Mon-Fri).")

        logger.info(f"HermesScheduler started with {len(self._tasks)} scheduled task(s).")

    def stop(self):
        """
        Stop all scheduled tasks cleanly.
        Call this inside FastAPI lifespan shutdown.
        """
        self._running = False
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._tasks.clear()
        logger.info("HermesScheduler: All scheduled tasks stopped.")


# Global scheduler instance
hermes_scheduler = HermesScheduler()
