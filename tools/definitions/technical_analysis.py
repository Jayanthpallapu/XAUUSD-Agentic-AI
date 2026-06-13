import json
import logging
import pandas as pd
from langchain_core.tools import tool
from tools.definitions.market_data import fetch_ohlcv_data

__all__ = ["fetch_ohlcv_data", "analyze_price_structure"]

logger = logging.getLogger("technical_analysis_tools")


@tool
def analyze_price_structure(
    ohlcv_data: str = "", ohlcv_json: str = "", timeframe: str = "1D"
) -> str:
    """
    Given a JSON string of OHLCV candlestick data (sorted ascending by datetime),
    uses rule-based logic to analyze price structure and identify:
    - Trend direction (BULLISH, BEARISH, or RANGING)
    - Nearest Support and Resistance price zones
    - Market structure (HH/HL for uptrend, LH/LL for downtrend, or Ranging)
    - Bullish or Bearish Order Blocks
    - Common candlestick patterns (e.g. Doji, Hammer, Engulfing)
    Returns a text summary detailing the technical condition for the given timeframe.
    """
    data_to_parse = ohlcv_json if ohlcv_json else ohlcv_data
    try:
        candles = json.loads(data_to_parse)
    except Exception as e:
        logger.error(f"Failed to parse OHLCV data JSON: {e}")
        return f"Error: Invalid OHLCV data format. {str(e)}"

    if not isinstance(candles, list) or not candles:
        return "Error: Empty or non-list OHLCV data provided."

    df = pd.DataFrame(candles)
    required_cols = ["datetime", "open", "high", "low", "close"]
    for col in required_cols:
        if col not in df.columns:
            return f"Error: Missing column '{col}' in OHLCV data."

        df[col] = df[col].astype(float) if col != "datetime" else df[col]

    n_bars = len(df)
    if n_bars < 5:
        return f"Error: Too few bars ({n_bars}) for technical analysis. Need at least 5 bars."

    # 1. Trend Direction via SMA
    close_prices = df["close"]
    sma_20 = close_prices.rolling(window=min(20, n_bars)).mean().iloc[-1]
    sma_50 = close_prices.rolling(window=min(50, n_bars)).mean().iloc[-1]
    last_close = close_prices.iloc[-1]

    if last_close > sma_20 and last_close > sma_50:
        trend = "BULLISH"
    elif last_close < sma_20 and last_close < sma_50:
        trend = "BEARISH"
    else:
        trend = "RANGING"

    # 2. Support and Resistance levels (local minima and maxima)
    window = 2
    supports = []
    resistances = []

    for i in range(window, n_bars - window):
        low_val = df["low"].iloc[i]
        high_val = df["high"].iloc[i]

        # Check if local low (Support)
        is_support = True
        for j in range(-window, window + 1):
            if df["low"].iloc[i + j] < low_val:
                is_support = False
                break
        if is_support:
            supports.append(low_val)

        # Check if local high (Resistance)
        is_resistance = True
        for j in range(-window, window + 1):
            if df["high"].iloc[i + j] > high_val:
                is_resistance = False
                break
        if is_resistance:
            resistances.append(high_val)

    # Filter/Select closest support and resistance to last close
    nearest_support = None
    nearest_resistance = None

    below_close = [s for s in supports if s < last_close]
    above_close = [r for r in resistances if r > last_close]

    if below_close:
        nearest_support = max(below_close)
    else:
        nearest_support = df["low"].min()

    if above_close:
        nearest_resistance = min(above_close)
    else:
        nearest_resistance = df["high"].max()

    # 3. Market Structure
    recent_lows = [
        df["low"].iloc[i]
        for i in range(2, n_bars - 2)
        if all(df["low"].iloc[i] <= df["low"].iloc[i + j] for j in [-2, -1, 1, 2])
    ][-3:]
    recent_highs = [
        df["high"].iloc[i]
        for i in range(2, n_bars - 2)
        if all(df["high"].iloc[i] >= df["high"].iloc[i + j] for j in [-2, -1, 1, 2])
    ][-3:]

    structure_type = "Ranging"
    if len(recent_highs) >= 2 and len(recent_lows) >= 2:
        if recent_highs[-1] > recent_highs[-2] and recent_lows[-1] > recent_lows[-2]:
            structure_type = "HH/HL (uptrend)"
        elif recent_highs[-1] < recent_highs[-2] and recent_lows[-1] < recent_lows[-2]:
            structure_type = "LH/LL (downtrend)"
        else:
            structure_type = "Mixed Structure"

    # 4. Order Blocks (OB)
    order_block_msg = "No clear order blocks detected."
    for i in range(n_bars - 5, 1, -1):
        prev_candle = df.iloc[i]
        curr_candles = df.iloc[i + 1 :]
        atr = (df["high"] - df["low"]).mean()

        # Bullish OB: prev is red, next candles make a strong move up
        if prev_candle["close"] < prev_candle["open"]:
            max_close = curr_candles["close"].max()
            if max_close > prev_candle["high"] + atr:
                order_block_msg = f"Bullish Order Block at ${prev_candle['low']:.2f} - ${prev_candle['open']:.2f} (created at {prev_candle['datetime']})"
                break
        # Bearish OB: prev is green, next candles make a strong move down
        elif prev_candle["close"] > prev_candle["open"]:
            min_close = curr_candles["close"].min()
            if min_close < prev_candle["low"] - atr:
                order_block_msg = f"Bearish Order Block at ${prev_candle['open']:.2f} - ${prev_candle['high']:.2f} (created at {prev_candle['datetime']})"
                break

    # 5. Candlestick patterns
    pattern_detected = "None"
    last_candle = df.iloc[-1]
    prev_candle = df.iloc[-2]

    body_size = abs(last_candle["close"] - last_candle["open"])
    range_size = last_candle["high"] - last_candle["low"]

    # Doji
    if range_size > 0 and (body_size / range_size) < 0.1:
        pattern_detected = "Doji (Indecision)"
    # Hammer / Shooting Star
    elif range_size > 0:
        lower_shadow = (
            min(last_candle["open"], last_candle["close"]) - last_candle["low"]
        )
        upper_shadow = last_candle["high"] - max(
            last_candle["open"], last_candle["close"]
        )
        if lower_shadow / range_size > 0.6 and body_size / range_size < 0.35:
            pattern_detected = "Bullish Hammer / Pin Bar"
        elif upper_shadow / range_size > 0.6 and body_size / range_size < 0.35:
            pattern_detected = "Bearish Shooting Star / Pin Bar"

    # Engulfing
    if pattern_detected == "None":
        if (
            prev_candle["close"] < prev_candle["open"]
            and last_candle["close"] > last_candle["open"]
        ):
            if (
                last_candle["open"] <= prev_candle["close"]
                and last_candle["close"] >= prev_candle["open"]
            ):
                pattern_detected = "Bullish Engulfing"
        elif (
            prev_candle["close"] > prev_candle["open"]
            and last_candle["close"] < last_candle["open"]
        ):
            if (
                last_candle["open"] >= prev_candle["close"]
                and last_candle["close"] <= prev_candle["open"]
            ):
                pattern_detected = "Bearish Engulfing"

    analysis_narrative = (
        f"Technical conditions on {timeframe} timeframe:\n"
        f"- Trend Bias: {trend} (Last Close: ${last_close:.2f}, SMA 20: ${sma_20:.2f}, SMA 50: ${sma_50:.2f})\n"
        f"- Market Structure: {structure_type}\n"
        f"- Key Levels: Support: ${nearest_support:.2f} | Resistance: ${nearest_resistance:.2f}\n"
        f"- Order Block: {order_block_msg}\n"
        f"- Last Candle Pattern: {pattern_detected}"
    )

    return analysis_narrative
