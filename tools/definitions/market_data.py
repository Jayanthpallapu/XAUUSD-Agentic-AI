import logging
import json
import requests
from langchain_core.tools import tool
from config import settings

logger = logging.getLogger("market_data_tools")

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance not installed. Using API fallbacks.")


@tool
def fetch_gold_price() -> str:
    """Fetches the current real-time or near-real-time gold price (XAU/USD) in USD."""
    if settings.TWELVE_DATA_API_KEY and "your_twelve" not in settings.TWELVE_DATA_API_KEY.lower():
        try:
            url = f"https://api.twelvedata.com/price?symbol=XAU/USD&apikey={settings.TWELVE_DATA_API_KEY}"
            res = requests.get(url, timeout=10)
            data = res.json()
            if "price" in data:
                return f"Gold (XAU/USD) Price: ${float(data['price']):.2f} USD (via Twelve Data)"
        except Exception as e:
            logger.error(f"Twelve Data gold fetch failed: {e}")

    if YFINANCE_AVAILABLE:
        try:
            ticker = yf.Ticker("GC=F")
            price = ticker.fast_info.last_price
            if price:
                return f"Gold (XAU/USD) Futures Price: ${price:.2f} USD (via yfinance GC=F)"
        except Exception as e:
            logger.error(f"yfinance gold fetch failed: {e}")

    return "Gold (XAU/USD) Price: $2645.30 USD (Mock Spot Price)"


@tool
def fetch_forex_prices(pairs: str = "EURUSD,USDJPY,GBPUSD,USDCHF,AUDUSD") -> str:
    """
    Fetches the current exchange rate for key forex currency pairs.
    Input should be a comma-separated list of pairs, e.g., 'EURUSD,USDJPY'.
    """
    pair_list = [p.strip().upper() for p in pairs.split(",")]
    results = []

    if settings.TWELVE_DATA_API_KEY and "your_twelve" not in settings.TWELVE_DATA_API_KEY.lower():
        try:
            formatted_pairs = ",".join([f"{p[:3]}/{p[3:]}" for p in pair_list if len(p) == 6])
            url = f"https://api.twelvedata.com/price?symbol={formatted_pairs}&apikey={settings.TWELVE_DATA_API_KEY}"
            res = requests.get(url, timeout=10)
            data = res.json()
            if isinstance(data, dict) and "price" in data:
                return f"{pairs}: {data['price']} (via Twelve Data)"
            elif isinstance(data, dict):
                for p_key, p_val in data.items():
                    if isinstance(p_val, dict) and "price" in p_val:
                        results.append(f"{p_key.replace('/', '')}: {float(p_val['price']):.4f}")
            if results:
                return "Forex Rates: " + ", ".join(results) + " (via Twelve Data)"
        except Exception as e:
            logger.error(f"Twelve Data forex fetch failed: {e}")

    try:
        url = "https://api.frankfurter.dev/latest?from=USD"
        res = requests.get(url, timeout=10)
        data = res.json()
        rates = data.get("rates", {})
        frankfurter_rates = []
        for pair in pair_list:
            if pair.startswith("USD") and len(pair) == 6:
                target = pair[3:]
                if target in rates:
                    frankfurter_rates.append(f"{pair}: {rates[target]:.4f}")
            elif pair.endswith("USD") and len(pair) == 6:
                base = pair[:3]
                if base in rates:
                    frankfurter_rates.append(f"{pair}: {1.0 / rates[base]:.4f}")
        if frankfurter_rates:
            return "Forex Rates (Daily ECB): " + ", ".join(frankfurter_rates) + " (via Frankfurter API)"
    except Exception as e:
        logger.error(f"Frankfurter forex fetch failed: {e}")

    mock_rates = {"EURUSD": "1.0850", "USDJPY": "154.20", "GBPUSD": "1.2680", "USDCHF": "0.8920", "AUDUSD": "0.6640"}
    returned_mocks = [f"{p}: {mock_rates.get(p, '1.0000')}" for p in pair_list]
    return "Forex Rates: " + ", ".join(returned_mocks) + " (Mock Rates)"


@tool
def fetch_commodities_prices() -> str:
    """Fetches the current prices of correlated commodities: Silver (XAGUSD), WTI Crude Oil, Brent Crude Oil, and Copper."""
    results = []
    if YFINANCE_AVAILABLE:
        tickers = {"Silver (XAG/USD)": "SI=F", "WTI Crude Oil": "CL=F", "Brent Crude Oil": "BZ=F", "Copper": "HG=F"}
        for name, ticker_sym in tickers.items():
            try:
                ticker = yf.Ticker(ticker_sym)
                price = ticker.fast_info.last_price
                if price:
                    results.append(f"{name}: ${price:.2f}")
            except Exception as e:
                logger.error(f"yfinance failed for {name}: {e}")
    if results:
        return "Commodity Prices: " + ", ".join(results) + " (via yfinance Futures)"
    return "Commodity Prices: Silver: $30.50, WTI: $78.20, Brent: $82.40, Copper: $4.15 (Mock)"


@tool
def fetch_crypto_prices() -> str:
    """Fetches the current price of Bitcoin (BTC) in USD."""
    if settings.COINGECKO_API_KEY:
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&x_cg_demo_api_key={settings.COINGECKO_API_KEY}"
            res = requests.get(url, timeout=10)
            data = res.json()
            if "bitcoin" in data and "usd" in data["bitcoin"]:
                return f"Bitcoin (BTC/USD): ${data['bitcoin']['usd']:,} USD (via CoinGecko)"
        except Exception as e:
            logger.error(f"CoinGecko fetch failed: {e}")
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        res = requests.get(url, timeout=10)
        data = res.json()
        if "bitcoin" in data and "usd" in data["bitcoin"]:
            return f"Bitcoin (BTC/USD): ${data['bitcoin']['usd']:,} USD (via CoinGecko Public)"
    except Exception as e:
        logger.error(f"CoinGecko public fetch failed: {e}")
    if YFINANCE_AVAILABLE:
        try:
            ticker = yf.Ticker("BTC-USD")
            price = ticker.fast_info.last_price
            if price:
                return f"Bitcoin (BTC/USD): ${price:,.2f} USD (via yfinance)"
        except Exception as e:
            logger.error(f"yfinance BTC fetch failed: {e}")
    return "Bitcoin (BTC/USD): $67,450.00 USD (Mock Price)"


@tool
def fetch_market_indices() -> str:
    """Fetches the US Dollar Index (DXY), S&P 500, and VIX volatility index."""
    results = []
    if YFINANCE_AVAILABLE:
        tickers = {"US Dollar Index (DXY)": "DX-Y.NYB", "S&P 500": "^GSPC", "VIX": "^VIX"}
        for name, ticker_sym in tickers.items():
            try:
                ticker = yf.Ticker(ticker_sym)
                price = ticker.fast_info.last_price
                if price:
                    results.append(f"{name}: {price:.2f}")
            except Exception as e:
                logger.error(f"yfinance index {name} failed: {e}")
    if results:
        return "Market Indices: " + ", ".join(results) + " (via yfinance)"
    return "Market Indices: DXY: 104.50, S&P 500: 5300.20, VIX: 13.50 (Mock)"


@tool
def fetch_treasury_yields() -> str:
    """Fetches the current US 10-Year Treasury Bond yield and 2-Year yield (yield curve)."""
    if settings.FRED_API_KEY:
        try:
            url10 = f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&limit=1&sort_order=desc&file_type=json&api_key={settings.FRED_API_KEY}"
            url2 = f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS2&limit=1&sort_order=desc&file_type=json&api_key={settings.FRED_API_KEY}"
            r10 = requests.get(url10, timeout=10).json()
            r2 = requests.get(url2, timeout=10).json()
            y10 = r10.get("observations", [{}])[0].get("value", "N/A")
            y2 = r2.get("observations", [{}])[0].get("value", "N/A")
            spread = round(float(y10) - float(y2), 3) if y10 != "N/A" and y2 != "N/A" else "N/A"
            return f"US 10Y Yield: {y10}% | US 2Y Yield: {y2}% | Spread: {spread}% (via FRED)"
        except Exception as e:
            logger.error(f"FRED API yields fetch failed: {e}")
    if YFINANCE_AVAILABLE:
        try:
            ticker = yf.Ticker("^TNX")
            price = ticker.fast_info.last_price
            if price:
                yield_val = price / 10.0 if price > 15.0 else price
                return f"US 10-Year Treasury Yield: {yield_val:.3f}% (via yfinance ^TNX)"
        except Exception as e:
            logger.error(f"yfinance yield fetch failed: {e}")
    return "US 10-Year Treasury Yield: 4.425% (Mock Yield)"


@tool
def fetch_finnhub_news() -> str:
    """
    Fetches the latest gold and forex market news from Finnhub.
    Uses the FINNHUB_API_KEY for live news sentiment and headlines.
    Returns top 8 recent news items relevant to gold (XAUUSD) and macro markets.
    """
    if not settings.FINNHUB_API_KEY:
        return "Finnhub API key not configured."
    try:
        import time
        to_ts = int(time.time())
        from_ts = to_ts - 86400  # Last 24 hours
        url = f"https://finnhub.io/api/v1/news?category=forex&token={settings.FINNHUB_API_KEY}"
        res = requests.get(url, timeout=10)
        data = res.json()
        if not isinstance(data, list):
            return f"Finnhub news error: {data}"
        gold_keywords = ["gold", "xau", "fed", "fomc", "inflation", "cpi", "dollar", "dxy", "yields", "rate", "recession", "geopolit"]
        filtered = [item for item in data if any(kw in item.get("headline", "").lower() or kw in item.get("summary", "").lower() for kw in gold_keywords)]
        items = filtered[:8] if filtered else data[:8]
        if not items:
            return "No recent news from Finnhub for gold/macro keywords."
        lines = []
        for item in items:
            headline = item.get("headline", "")
            source = item.get("source", "Finnhub")
            related = item.get("related", "")
            lines.append(f"• [{source}] {headline}")
        return f"📰 Finnhub Market News (Live):\n\n" + "\n".join(lines) + "\n\nSource: finnhub.io"
    except Exception as e:
        logger.error(f"Finnhub news fetch failed: {e}")
        return f"Finnhub news fetch error: {str(e)}"


@tool
def fetch_alpha_vantage_sentiment() -> str:
    """
    Fetches official gold and forex news sentiment from Alpha Vantage.
    Returns sentiment scores and recent headlines from professional financial news sources.
    Uses ALPHA_VANTAGE_API_KEY.
    """
    if not settings.ALPHA_VANTAGE_API_KEY:
        return "Alpha Vantage API key not configured."
    try:
        url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers=FOREX:XAU,FOREX:USD&apikey={settings.ALPHA_VANTAGE_API_KEY}"
        res = requests.get(url, timeout=10)
        data = res.json()
        feed = data.get("feed", [])
        if not feed:
            return "Alpha Vantage: No news sentiment data returned."
        sentiment_sum = 0.0
        bullish_count = 0
        bearish_count = 0
        headlines = []
        for item in feed[:6]:
            score = float(item.get("overall_sentiment_score", 0.0))
            sentiment_sum += score
            label = item.get("overall_sentiment_label", "Neutral")
            if "Bullish" in label:
                bullish_count += 1
            elif "Bearish" in label:
                bearish_count += 1
            headlines.append(f"- {item.get('title', '')} ({label}, Score: {score:.2f})")
        avg_sentiment = sentiment_sum / max(1, len(feed[:6]))
        overall = "Bullish" if avg_sentiment > 0.15 else "Bearish" if avg_sentiment < -0.15 else "Neutral"
        return (
            f"Alpha Vantage Market Sentiment: {overall} (Avg: {avg_sentiment:.2f})\n"
            f"Bullish: {bullish_count} | Bearish: {bearish_count}\n"
            f"Recent Headlines:\n" + "\n".join(headlines)
        )
    except Exception as e:
        logger.error(f"Alpha Vantage sentiment failed: {e}")
        return f"Alpha Vantage error: {str(e)}"
