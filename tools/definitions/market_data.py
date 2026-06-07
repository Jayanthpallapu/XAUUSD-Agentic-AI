import logging
import requests
from crewai.tools import tool
from config import settings

logger = logging.getLogger("market_data_tools")

# Optional yfinance import
try:
    import yfinance as yf

    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance package not installed. Using raw requests/API fallbacks.")


@tool("Gold Price Fetcher")
def fetch_gold_price() -> str:
    """Fetches the current real-time or near-real-time gold price (XAU/USD) in USD."""
    # Try Twelve Data first if configured
    if settings.TWELVE_DATA_API_KEY:
        try:
            url = f"https://api.twelvedata.com/price?symbol=XAU/USD&apikey={settings.TWELVE_DATA_API_KEY}"
            res = requests.get(url, timeout=10)
            data = res.json()
            if "price" in data:
                return f"Gold (XAU/USD) Price: ${float(data['price']):.2f} USD (via Twelve Data)"
        except Exception as e:
            logger.error(f"Twelve Data gold fetch failed: {e}")

    # Fallback to yfinance (GC=F is Gold Futures on Yahoo)
    if YFINANCE_AVAILABLE:
        try:
            ticker = yf.Ticker("GC=F")
            info = ticker.fast_info
            price = info.get("last_price")
            if price:
                return f"Gold (XAU/USD) Futures Price: ${price:.2f} USD (via yfinance ticker GC=F)"
        except Exception as e:
            logger.error(f"yfinance gold futures fetch failed: {e}")

    # Final hardcoded mock for offline/fail safety
    return "Gold (XAU/USD) Price: $2645.30 USD (Mock Spot Price)"


@tool("Forex Pairs Price Fetcher")
def fetch_forex_prices(pairs: str = "EURUSD,USDJPY,GBPUSD,USDCHF,AUDUSD") -> str:
    """
    Fetches the current exchange rate for key forex currency pairs.
    Input should be a comma-separated list of pairs, e.g., 'EURUSD,USDJPY'.
    """
    pair_list = [p.strip().upper() for p in pairs.split(",")]
    results = []

    # Try Twelve Data
    if settings.TWELVE_DATA_API_KEY:
        try:
            formatted_pairs = ",".join(
                [f"{p[:3]}/{p[3:]}" for p in pair_list if len(p) == 6]
            )
            url = f"https://api.twelvedata.com/price?symbol={formatted_pairs}&apikey={settings.TWELVE_DATA_API_KEY}"
            res = requests.get(url, timeout=10)
            data = res.json()

            # Twelve data returns dict if single pair, list of dicts if multiple
            if isinstance(data, dict) and "price" in data:
                return f"{pairs}: {data['price']} (via Twelve Data)"
            elif isinstance(data, dict):
                for p_key, p_val in data.items():
                    if "price" in p_val:
                        results.append(
                            f"{p_key.replace('/', '')}: {float(p_val['price']):.4f}"
                        )
            if results:
                return "Forex Rates: " + ", ".join(results) + " (via Twelve Data)"
        except Exception as e:
            logger.error(f"Twelve Data forex fetch failed: {e}")

    # Try Frankfurter API (Free, no key needed)
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
                    rate = 1.0 / rates[base]
                    frankfurter_rates.append(f"{pair}: {rate:.4f}")

        if frankfurter_rates:
            return (
                "Forex Rates (Daily ECB): "
                + ", ".join(frankfurter_rates)
                + " (via Frankfurter API)"
            )
    except Exception as e:
        logger.error(f"Frankfurter forex fetch failed: {e}")

    # Fallback mock rates
    mock_rates = {
        "EURUSD": "1.0850",
        "USDJPY": "154.20",
        "GBPUSD": "1.2680",
        "USDCHF": "0.8920",
        "AUDUSD": "0.6640",
    }
    returned_mocks = [f"{p}: {mock_rates.get(p, '1.0000')}" for p in pair_list]
    return "Forex Rates: " + ", ".join(returned_mocks) + " (Mock Rates)"


@tool("Commodities Price Fetcher")
def fetch_commodities_prices() -> str:
    """Fetches the current prices of correlated commodities: Silver (XAGUSD), WTI Crude Oil, Brent Crude Oil, and Copper."""
    results = []

    # Use yfinance
    if YFINANCE_AVAILABLE:
        tickers = {
            "Silver (XAG/USD)": "SI=F",
            "WTI Crude Oil": "CL=F",
            "Brent Crude Oil": "BZ=F",
            "Copper": "HG=F",
        }
        for name, ticker_sym in tickers.items():
            try:
                ticker = yf.Ticker(ticker_sym)
                price = ticker.fast_info.get("last_price")
                if price:
                    results.append(f"{name}: ${price:.2f}")
            except Exception as e:
                logger.error(f"yfinance failed for {name}: {e}")

    if results:
        return "Commodity Prices: " + ", ".join(results) + " (via yfinance Futures)"

    return "Commodity Prices: Silver (XAG/USD): $30.50, WTI Crude: $78.20, Brent Crude: $82.40, Copper: $4.15 (Mock Prices)"


@tool("Crypto Price Fetcher")
def fetch_crypto_prices() -> str:
    """Fetches the current price of Bitcoin (BTC) in USD."""
    # CoinGecko Demo API
    if settings.COINGECKO_API_KEY:
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&x_cg_demo_api_key={settings.COINGECKO_API_KEY}"
            res = requests.get(url, timeout=10)
            data = res.json()
            if "bitcoin" in data and "usd" in data["bitcoin"]:
                return f"Bitcoin (BTC/USD) Price: ${data['bitcoin']['usd']:,} USD (via CoinGecko)"
        except Exception as e:
            logger.error(f"CoinGecko fetch failed: {e}")

    # No key CoinGecko public API
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        res = requests.get(url, timeout=10)
        data = res.json()
        if "bitcoin" in data and "usd" in data["bitcoin"]:
            return f"Bitcoin (BTC/USD) Price: ${data['bitcoin']['usd']:,} USD (via CoinGecko Public)"
    except Exception as e:
        logger.error(f"CoinGecko public fetch failed: {e}")

    # Try yfinance fallback (BTC-USD)
    if YFINANCE_AVAILABLE:
        try:
            ticker = yf.Ticker("BTC-USD")
            price = ticker.fast_info.get("last_price")
            if price:
                return f"Bitcoin (BTC/USD) Price: ${price:,.2f} USD (via yfinance)"
        except Exception as e:
            logger.error(f"yfinance BTC fetch failed: {e}")

    return "Bitcoin (BTC/USD) Price: $67,450.00 USD (Mock Price)"


@tool("Market Indices Fetcher")
def fetch_market_indices() -> str:
    """Fetches the current value of the Dollar Index (DXY), S&P 500 Index, and volatility index (VIX)."""
    results = []

    if YFINANCE_AVAILABLE:
        tickers = {
            "US Dollar Index (DXY)": "DX-Y.NYB",
            "S&P 500 (^GSPC)": "^GSPC",
            "CBOE Volatility Index (VIX)": "^VIX",
        }
        for name, ticker_sym in tickers.items():
            try:
                ticker = yf.Ticker(ticker_sym)
                price = ticker.fast_info.get("last_price")
                if price:
                    results.append(f"{name}: {price:.2f}")
            except Exception as e:
                logger.error(f"yfinance index {name} failed: {e}")

    if results:
        return "Market Indices: " + ", ".join(results) + " (via yfinance)"

    return "Market Indices: US Dollar Index (DXY): 104.50, S&P 500: 5300.20, VIX: 13.50 (Mock Indices)"


@tool("Treasury Yields Fetcher")
def fetch_treasury_yields() -> str:
    """Fetches the current yield of the US 10-Year Treasury Bond (US10Y)."""
    if settings.FRED_API_KEY:
        try:
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&limit=1&sort_order=desc&file_type=json&api_key={settings.FRED_API_KEY}"
            res = requests.get(url, timeout=10)
            data = res.json()
            observations = data.get("observations", [])
            if observations:
                val = observations[0].get("value")
                return f"US 10-Year Treasury Yield: {val}% (via FRED Series DGS10)"
        except Exception as e:
            logger.error(f"FRED API yields fetch failed: {e}")

    if YFINANCE_AVAILABLE:
        try:
            ticker = yf.Ticker("^TNX")
            price = ticker.fast_info.get("last_price")
            if price:
                yield_val = price / 10.0
                return f"US 10-Year Treasury Yield: {yield_val:.3f}% (via yfinance ticker ^TNX)"
        except Exception as e:
            logger.error(f"yfinance yield fetch failed: {e}")

    return "US 10-Year Treasury Yield: 4.425% (Mock Yield)"
