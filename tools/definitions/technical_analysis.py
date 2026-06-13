"""
Technical Analysis Tool
========================
Fetches multi-timeframe OHLCV data from Twelve Data API and applies
rule-based technical analysis to identify:
  - Trend direction and market structure (HH/HL/LH/LL)
  - Support and resistance zones
  - Order blocks (last bearish/bullish engulfing before impulse move)
  - Liquidity zones (equal highs/lows)
  - Candlestick patterns (Engulfing, Pin Bar, Doji, Hammer)
  - Breakout detection
"""

import logging
import json
import requests
from langchain_core.tools import tool
from config import settings

logger = logging.getLogger("technical_analysis_tools")

# Interval mapping: agent timeframe name -> Twelve Data interval string
INTERVAL_MAP = {
    "1W": "1week",
    "1D": "1day",
    "4H": "4h",
    "1H": "1h",
    "15M": "15min",
    "5M": "5min",
}


def _fetch_ohlcv_twelvedata(symbol: str, interval: str, outputsize: int = 50) -> list:
    """Fetch OHLCV from Twelve Data API."""
    if (
        not settings.TWELVE_DATA_API_KEY
        or "your_twelve" in settings.TWELVE_DATA_API_KEY.lower()
    ):
        return []
    try:
        url = (
            f"https://api.twelvedata.com/time_series"
            f"?symbol={symbol}&interval={interval}&outputsize={outputsize}"
            f"&apikey={settings.TWELVE_DATA_API_KEY}&format=JSON"
        )
        res = requests.get(url, timeout=15)
        data = res.json()
        if "values" in data:
            return data["values"]
        logger.warning(f"Twelve Data OHLCV error: {data.get('message', data)}")
    except Exception as e:
        logger.error(f"Twelve Data OHLCV fetch failed: {e}")
    return []


def _fetch_ohlcv_yfinance(interval: str, period: str) -> list:
    """Fetch OHLCV from yfinance as fallback."""
    try:
        import yfinance as yf

        ticker = yf.Ticker("GC=F")
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            return []
        rows = []
        for ts, row in df.iterrows():
            rows.append(
                {
                    "datetime": str(ts),
                    "open": str(round(float(row["Open"]), 2)),
                    "high": str(round(float(row["High"]), 2)),
                    "low": str(round(float(row["Low"]), 2)),
                    "close": str(round(float(row["Close"]), 2)),
                    "volume": str(int(row["Volume"])),
                }
            )
        return list(reversed(rows))  # Most recent first
    except Exception as e:
        logger.error(f"yfinance OHLCV fallback failed: {e}")
    return []


YFINANCE_INTERVAL_MAP = {
    "1week": ("1wk", "2y"),
    "1day": ("1d", "6mo"),
    "4h": ("1h", "60d"),  # yfinance no 4h; use 1h and we process
    "1h": ("1h", "30d"),
    "15min": ("15m", "7d"),
    "5min": ("5m", "5d"),
}


@tool
def fetch_ohlcv_data(timeframe: str = "1H", bars: int = 50) -> str:
    """
    Fetches OHLCV candlestick data for XAU/USD (Gold) at a given timeframe.
    Timeframe must be one of: 1W, 1D, 4H, 1H, 15M, 5M.
    Returns JSON-formatted candlestick data with open, high, low, close, volume fields.
    The 'bars' parameter controls how many candles to return (default 50, max 100).
    """
    interval = INTERVAL_MAP.get(timeframe.upper(), "1h")
    bars = min(bars, 100)

    # Primary: Twelve Data
    candles = _fetch_ohlcv_twelvedata("XAU/USD", interval, outputsize=bars)

    # Fallback: yfinance
    if not candles:
        yf_interval, yf_period = YFINANCE_INTERVAL_MAP.get(interval, ("1h", "7d"))
        candles = _fetch_ohlcv_yfinance(yf_interval, yf_period)

    if not candles:
        return f"OHLCV data unavailable for {timeframe}. Using mock: Gold ranging near $2640-2660."

    # Return as compact JSON string (agents parse this for analysis)
    return json.dumps(
        {
            "symbol": "XAU/USD",
            "timeframe": timeframe,
            "interval": interval,
            "bars": len(candles),
            "candles": candles[:bars],
        }
    )


@tool
def analyze_price_structure(ohlcv_json: str, timeframe: str = "1H") -> str:
    """
    Analyzes OHLCV candlestick data to identify technical structure for XAU/USD.
    Pass the JSON string output from fetch_ohlcv_data as the ohlcv_json argument.
    Returns trend direction, market structure (HH/HL or LH/LL), support/resistance,
    order blocks, liquidity zones, and candlestick patterns.
    """
    try:
        data = json.loads(ohlcv_json)
        candles = data.get("candles", [])
        if len(candles) < 10:
            return f"Insufficient candle data for {timeframe} analysis (need 10+, got {len(candles)})."

        # Parse candles (most recent first from Twelve Data)
        closes = [float(c["close"]) for c in candles]
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        opens = [float(c["open"]) for c in candles]

        current_price = closes[0]
        recent_closes = closes[:20]
        recent_highs = highs[:20]
        recent_lows = lows[:20]

        # ── Trend (simple EMA crossover proxy)
        ema_fast = sum(recent_closes[:5]) / 5
        ema_slow = sum(recent_closes[:20]) / 20
        if ema_fast > ema_slow * 1.001:
            trend = "BULLISH"
        elif ema_fast < ema_slow * 0.999:
            trend = "BEARISH"
        else:
            trend = "RANGING"

        # ── Market structure (HH/HL vs LH/LL)
        swings = []
        for i in range(2, min(15, len(candles) - 2)):
            if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
                swings.append(("H", highs[i]))
            elif lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
                swings.append(("L", lows[i]))

        prev_highs = [v for t, v in swings if t == "H"][:3]
        prev_lows = [v for t, v in swings if t == "L"][:3]
        structure = "ranging"
        if len(prev_highs) >= 2 and len(prev_lows) >= 2:
            if prev_highs[0] > prev_highs[1] and prev_lows[0] > prev_lows[1]:
                structure = "HH/HL — Uptrend"
            elif prev_highs[0] < prev_highs[1] and prev_lows[0] < prev_lows[1]:
                structure = "LH/LL — Downtrend"
            else:
                structure = "Mixed — Transitional"

        # ── Support & Resistance
        resistance = round(max(recent_highs[:10]), 2)
        support = round(min(recent_lows[:10]), 2)
        mid = round((resistance + support) / 2, 2)

        # ── Order Block Detection (last bearish candle before bullish impulse / vice versa)
        order_block = "None detected"
        for i in range(1, min(10, len(candles) - 1)):
            body_curr = closes[i] - opens[i]
            body_prev = closes[i + 1] - opens[i + 1]
            # Bullish OB: bearish candle followed by strong bullish move
            if body_prev < 0 and body_curr > abs(body_prev) * 1.5:
                ob_low = min(opens[i + 1], closes[i + 1])
                ob_high = max(opens[i + 1], closes[i + 1])
                order_block = f"Bullish OB at ${ob_low:.2f}-${ob_high:.2f} (unmitigated demand zone)"
                break
            # Bearish OB: bullish candle followed by strong bearish move
            if body_prev > 0 and body_curr < -abs(body_prev) * 1.5:
                ob_low = min(opens[i + 1], closes[i + 1])
                ob_high = max(opens[i + 1], closes[i + 1])
                order_block = f"Bearish OB at ${ob_low:.2f}-${ob_high:.2f} (unmitigated supply zone)"
                break

        # ── Liquidity Zones (equal highs/lows within 0.1%)
        tol = 0.001
        liq_highs = [
            h
            for h in recent_highs
            if abs(h - max(recent_highs)) / max(recent_highs) < tol
        ]
        liq_lows = [
            lval for lval in recent_lows if abs(lval - min(recent_lows)) / min(recent_lows) < tol
        ]
        liquidity_zone = "None"
        if len(liq_highs) >= 2:
            liquidity_zone = (
                f"Buy-side liquidity above ${max(liq_highs):.2f} (equal highs)"
            )
        elif len(liq_lows) >= 2:
            liquidity_zone = (
                f"Sell-side liquidity below ${min(liq_lows):.2f} (equal lows)"
            )

        # ── Candlestick Pattern (last 2 candles)
        c0_body = closes[0] - opens[0]
        c0_range = highs[0] - lows[0]
        c1_body = closes[1] - opens[1]
        pattern = "None"
        if c0_range > 0:
            if abs(c0_body) < c0_range * 0.1:
                pattern = "Doji — indecision"
            elif c0_body > 0 and c1_body < 0 and abs(c0_body) > abs(c1_body):
                pattern = "Bullish Engulfing"
            elif c0_body < 0 and c1_body > 0 and abs(c0_body) > abs(c1_body):
                pattern = "Bearish Engulfing"
            elif c0_body > 0 and (closes[0] - lows[0]) > abs(c0_body) * 2:
                pattern = "Hammer / Bullish Pin Bar"
            elif c0_body < 0 and (highs[0] - opens[0]) > abs(c0_body) * 2:
                pattern = "Shooting Star / Bearish Pin Bar"

        # ── Breakout Detection
        breakout = "No breakout detected"
        if closes[0] > resistance:
            breakout = f"Bullish breakout above ${resistance:.2f} resistance"
        elif closes[0] < support:
            breakout = f"Bearish breakdown below ${support:.2f} support"

        return (
            f"=== Technical Analysis: {timeframe} ({data.get('symbol', 'XAU/USD')}) ===\n"
            f"Current Price: ${current_price:.2f}\n"
            f"Trend: {trend}\n"
            f"Market Structure: {structure}\n"
            f"Key Resistance: ${resistance:.2f}\n"
            f"Key Support: ${support:.2f}\n"
            f"Midpoint: ${mid:.2f}\n"
            f"Order Block: {order_block}\n"
            f"Liquidity Zone: {liquidity_zone}\n"
            f"Candlestick Pattern: {pattern}\n"
            f"Breakout: {breakout}\n"
        )
    except Exception as e:
        logger.error(f"Price structure analysis error: {e}")
        return f"Error analyzing price structure: {str(e)}"
