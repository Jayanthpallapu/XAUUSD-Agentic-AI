import logging
import uuid
from datetime import datetime
from crewai.tools import tool
from governance.audit.supabase_client import db_service

logger = logging.getLogger("trading_performance_tools")


@tool("Paper Trade Executor")
def execute_paper_trade(
    direction: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    confidence_score: float,
    reasoning: str,
    cycle_id: str = "",
) -> str:
    """
    Executes a simulated paper trade for XAUUSD (Gold).
    Input details:
      - direction: 'BUY', 'SELL', or 'HOLD'
      - entry_price: Float value (e.g. 2645.50)
      - stop_loss: Float value (e.g. 2635.00)
      - take_profit: Float value (e.g. 2665.00)
      - confidence_score: Float confidence between 0.0 and 1.0 (e.g. 0.85)
      - reasoning: Explanation for the entry
      - cycle_id: Optional UUID string representing the current analysis cycle
    """
    direction = direction.upper().strip()
    if direction not in ["BUY", "SELL", "HOLD"]:
        return "Trade Execution Failed: Invalid direction. Must be BUY, SELL, or HOLD."

    if direction == "HOLD":
        return "No trade executed. Cycle decision is HOLD. Monitoring market for next setup."

    if entry_price <= 0 or stop_loss <= 0 or take_profit <= 0:
        return "Trade Execution Failed: Prices must be positive."

    if direction == "BUY":
        if stop_loss >= entry_price:
            return f"Trade Execution Failed: Stop Loss (${stop_loss}) must be below Entry Price (${entry_price}) for BUY orders."
        if take_profit <= entry_price:
            return f"Trade Execution Failed: Take Profit (${take_profit}) must be above Entry Price (${entry_price}) for BUY orders."
    elif direction == "SELL":
        if stop_loss <= entry_price:
            return f"Trade Execution Failed: Stop Loss (${stop_loss}) must be above Entry Price (${entry_price}) for SELL orders."
        if take_profit >= entry_price:
            return f"Trade Execution Failed: Take Profit (${take_profit}) must be below Entry Price (${entry_price}) for SELL orders."

    trade_id = str(uuid.uuid4())
    trade_data = {
        "id": trade_id,
        "direction": direction,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "confidence_score": confidence_score,
        "reasoning": reasoning,
        "status": "active",
        "opened_at": datetime.utcnow().isoformat(),
        "close_price": None,
        "pnl_pips": 0.0,
        "pnl_usd": 0.0,
    }

    if cycle_id:
        trade_data["cycle_id"] = cycle_id

    try:
        db_service.insert("trade_signals", trade_data)

        risk_pips = abs(entry_price - stop_loss) * 10
        reward_pips = abs(take_profit - entry_price) * 10
        rr_ratio = reward_pips / risk_pips if risk_pips > 0 else 0.0

        lot_size = 0.5
        risk_usd = (risk_pips / 10.0) * (lot_size * 100)

        return (
            f"✅ SIMULATED TRADE PLACED SUCCESSFULLY!\n"
            f"Trade ID: {trade_id}\n"
            f"Direction: {direction}\n"
            f"Entry Spot Price: ${entry_price:.2f}\n"
            f"Stop Loss (SL): ${stop_loss:.2f} ({risk_pips:.1f} pips risk)\n"
            f"Take Profit (TP): ${take_profit:.2f} ({reward_pips:.1f} pips reward)\n"
            f"Risk/Reward Ratio: 1:{rr_ratio:.2f}\n"
            f"Position Size: {lot_size} lots (Estimated risk: ${risk_usd:.2f} on $10,000 account)\n"
            f"Reasoning: {reasoning}"
        )
    except Exception as e:
        logger.error(f"Error executing paper trade in DB: {e}")
        return f"Trade Execution Failed: DB insertion error. ({str(e)})"


@tool("Trade Performance Fetcher")
def fetch_trade_performance() -> str:
    """
    Fetches the history of paper trades and calculates performance metrics
    such as win rate, total PnL in USD, total trades, win/loss counts, and drawdown.
    """
    try:
        trades = db_service.select("trade_signals")

        if not trades:
            return (
                "--- Trading Performance Report ---\n"
                "Total Trades: 0\n"
                "Win Rate: 0.0%\n"
                "Total P&L: $0.00 USD\n"
                "No trade history available yet to compile metrics."
            )

        total_trades = len(trades)
        active_trades = [t for t in trades if t.get("status") == "active"]
        closed_trades = [
            t for t in trades if t.get("status") in ["closed_win", "closed_loss"]
        ]

        winning_trades = [t for t in closed_trades if t.get("status") == "closed_win"]
        losing_trades = [t for t in closed_trades if t.get("status") == "closed_loss"]

        win_count = len(winning_trades)
        loss_count = len(losing_trades)

        total_closed = len(closed_trades)
        win_rate = (win_count / total_closed * 100.0) if total_closed > 0 else 0.0

        total_pnl_usd = sum(float(t.get("pnl_usd", 0.0) or 0.0) for t in trades)

        starting_capital = 10000.0
        running_balance = starting_capital
        balances = [starting_capital]

        sorted_trades = sorted(
            [t for t in closed_trades if t.get("closed_at")],
            key=lambda x: x.get("closed_at"),
        )

        for t in sorted_trades:
            running_balance += float(t.get("pnl_usd", 0.0) or 0.0)
            balances.append(running_balance)

        peak = starting_capital
        max_drawdown_pct = 0.0
        for b in balances:
            if b > peak:
                peak = b
            drawdown = (peak - b) / peak * 100.0 if peak > 0 else 0.0
            if drawdown > max_drawdown_pct:
                max_drawdown_pct = drawdown

        total_gains = sum(float(t.get("pnl_usd", 0.0) or 0.0) for t in winning_trades)
        total_losses = abs(
            sum(float(t.get("pnl_usd", 0.0) or 0.0) for t in losing_trades)
        )
        profit_factor = (
            (total_gains / total_losses)
            if total_losses > 0
            else (total_gains if total_gains > 0 else 1.0)
        )

        return (
            f"--- Trading Performance Report ---\n"
            f"Account Starting Capital: $10,000.00 USD\n"
            f"Current Balance: ${starting_capital + total_pnl_usd:,.2f} USD\n"
            f"Total Trades Logged: {total_trades} ({len(active_trades)} Active, {total_closed} Closed)\n"
            f"Win/Loss: {win_count} Wins / {loss_count} Losses\n"
            f"Win Rate: {win_rate:.1f}%\n"
            f"Net P&L: ${total_pnl_usd:,.2f} USD\n"
            f"Profit Factor: {profit_factor:.2f}\n"
            f"Max Simulated Drawdown: {max_drawdown_pct:.2f}%\n"
        )
    except Exception as e:
        logger.error(f"Error fetching trade performance: {e}")
        return f"Error compiling performance report: {str(e)}"


@tool("Teacher Feedback Recorder")
def record_teacher_feedback(trade_id: str, notes: str) -> str:
    """
    Applies constructive educational feedback (teacher notes) to a specific trade.
    Used by the Supervisor Agent to document mistakes or trade improvement notes.
    """
    try:
        filters = {"id": trade_id}
        trades = db_service.select("trade_signals", filters)
        if not trades:
            return f"Error: Trade with ID {trade_id} not found."

        db_service.update("trade_signals", filters, {"teacher_notes": notes})

        db_service.save_lesson(
            agent_name="TradingAgent",
            mistake=f"Suboptimal trade placement on Trade ID {trade_id[:8]}",
            correction="Updated analysis confluence checks",
            lesson=notes,
        )

        return f"Constructive supervisor notes successfully applied to Trade ID {trade_id}. Lessons propagated to Agent memory."
    except Exception as e:
        logger.error(f"Error saving teacher feedback: {e}")
        return f"Error saving feedback: {str(e)}"
