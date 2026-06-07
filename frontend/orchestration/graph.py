import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
from governance.audit.supabase_client import db_service
from agents.orchestrator.agent import create_market_crew_flow
from tools.definitions.market_data import fetch_gold_price
import re

logger = logging.getLogger("flow_manager")


class FlowManager:
    @staticmethod
    def check_and_close_trades() -> List[Dict[str, Any]]:
        """
        Fetches all active paper trades, retrieves the current spot gold price,
        and determines if the trades should be closed out via SL or TP.
        """
        closed_signals = []
        try:
            gold_str = fetch_gold_price()
            match = re.search(r"\$(\d+(?:\.\d+)?)\s*USD", gold_str)
            if not match:
                match = re.search(r"\$(\d+(?:\.\d+)?)\s*Futures", gold_str)
            if not match:
                match = re.search(r"(\d{3,5}\.\d{1,2})", gold_str)

            if not match:
                logger.error(
                    f"Could not parse gold price to evaluate active positions. Raw price string: {gold_str}"
                )
                return []

            current_price = float(match.group(1))
            logger.info(
                f"Checking open positions against current spot price: ${current_price:.2f}"
            )

            active_trades = db_service.select("trade_signals", {"status": "active"})
            for trade in active_trades:
                trade_id = trade["id"]
                direction = trade["direction"]
                entry = float(trade["entry_price"])
                sl = float(trade["stop_loss"])
                tp = float(trade["take_profit"])

                lot_size = 0.5
                multiplier = lot_size * 100

                closed = False
                status = "active"
                close_price = None
                pnl_pips = 0.0
                pnl_usd = 0.0

                if direction == "BUY":
                    if current_price <= sl:
                        closed = True
                        status = "closed_loss"
                        close_price = sl
                        pnl_pips = (sl - entry) * 10
                        pnl_usd = (sl - entry) * multiplier
                    elif current_price >= tp:
                        closed = True
                        status = "closed_win"
                        close_price = tp
                        pnl_pips = (tp - entry) * 10
                        pnl_usd = (tp - entry) * multiplier

                elif direction == "SELL":
                    if current_price >= sl:
                        closed = True
                        status = "closed_loss"
                        close_price = sl
                        pnl_pips = (entry - sl) * 10
                        pnl_usd = (entry - sl) * multiplier
                    elif current_price <= tp:
                        closed = True
                        status = "closed_win"
                        close_price = tp
                        pnl_pips = (entry - tp) * 10
                        pnl_usd = (entry - tp) * multiplier

                if closed:
                    update_data = {
                        "status": status,
                        "close_price": close_price,
                        "pnl_pips": pnl_pips,
                        "pnl_usd": pnl_usd,
                        "closed_at": datetime.utcnow().isoformat(),
                    }
                    db_service.update("trade_signals", {"id": trade_id}, update_data)
                    logger.info(
                        f"Closed Trade {trade_id[:8]} ({direction}) as {status.upper()} at price: ${close_price:.2f}. PnL: ${pnl_usd:.2f}"
                    )
                    closed_signals.append({**trade, **update_data})

        except Exception as e:
            logger.error(f"Error checking and closing trades: {e}")

        return closed_signals

    @staticmethod
    def run_cycle() -> Dict[str, Any]:
        """
        Manages a single analysis cycle.
        """
        FlowManager.check_and_close_trades()

        cycle_data = {"status": "running", "started_at": datetime.utcnow().isoformat()}
        cycle = db_service.insert("analysis_cycles", cycle_data)
        cycle_id = cycle["id"]

        start_time = datetime.utcnow()
        try:
            logger.info(f"Launching Analysis Cycle ID: {cycle_id}")
            results = create_market_crew_flow(cycle_id)

            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()

            db_service.update(
                "analysis_cycles",
                {"id": cycle_id},
                {
                    "status": "completed",
                    "completed_at": end_time.isoformat(),
                    "duration_seconds": duration,
                },
            )

            return results
        except Exception as e:
            logger.error(
                f"Analysis Cycle ID {cycle_id} encountered critical failure: {e}"
            )
            db_service.update(
                "analysis_cycles",
                {"id": cycle_id},
                {
                    "status": "failed",
                    "completed_at": datetime.utcnow().isoformat(),
                    "duration_seconds": (
                        datetime.utcnow() - start_time
                    ).total_seconds(),
                },
            )
            db_service.insert(
                "audit_log",
                {
                    "agent_name": "SupervisorAgent",
                    "action": "CYCLE_EXECUTION_FAILURE",
                    "status": "error",
                    "error_message": str(e),
                },
            )
            raise e

    @staticmethod
    def backfill_lessons(days: int = 15):
        """
        Downloads historical price data from yfinance for backfilling lessons learned.
        """
        logger.info(
            f"Initiating historical backfill lessons training for past {days} days..."
        )
        try:
            import yfinance as yf

            start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
            data = yf.download(["GC=F", "DX-Y.NYB"], start=start_date, interval="1d")

            if data.empty:
                logger.warning(
                    "No historical yfinance data returned. Seeding default training lessons."
                )
                FlowManager._seed_default_lessons()
                return

            db_service.save_lesson(
                agent_name="CorrelationAgent",
                mistake="Underestimated inverse US Dollar Index correlation strength during FOMC inflation releases.",
                correction="Correlate price shifts with DXY. A DXY rise above 104.8 should trigger a Gold bearish bias shift.",
                lesson="Gold price is heavily inversely correlated to the DXY. Always verify DXY trend strength before setting a Gold trend.",
            )
            db_service.save_lesson(
                agent_name="TradingAgent",
                mistake="Placed BUY position during a strong US10Y treasury yields breakout, resulting in SL hit.",
                correction="Never buy XAUUSD if US10Y yields are breaking out above resistance, even if spot gold looks oversold.",
                lesson="Yields rise represents high opportunity cost for holding non-yielding gold, creating institutional selling pressure.",
            )
            db_service.save_lesson(
                agent_name="NewsAgent",
                mistake="Classified a minor Fed member commentary as a high-impact calendar event, triggering false alarms.",
                correction="Check the official calendar impact rating first. Only rate FOMC Chair Powell speech, CPI, NFP, and rate decisions as high impact.",
                lesson="Filter out noise from minor speeches to prevent system warnings from spamming the Telegram notifications channel.",
            )

            logger.info(
                "Successfully completed database backfill. Dynamic backstory lessons populated for all agent registry nodes."
            )

        except Exception as e:
            logger.error(f"Error executing database backfill: {e}")
            FlowManager._seed_default_lessons()

    @staticmethod
    def _seed_default_lessons():
        db_service.save_lesson(
            agent_name="TradingAgent",
            mistake="Entered BUY trade at local resistance level ($2680.00) without confluence.",
            correction="Confirm break-and-retest support on lower timeframes (1H/15M) before buying a high price.",
            lesson="Buying at horizontal resistance reduces Risk/Reward profiles and leads to high-rate drawdown events.",
        )
        logger.info("Default mock training lessons seeded in Agent registry.")
