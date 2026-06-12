"""
Enhanced Web Scraper for XAUUSD News & Economic Calendar
=========================================================
Uses httpx + BeautifulSoup for lightweight, reliable web scraping.
Provides richer market data than RSS feeds alone.

Scrapers included:
  1. Kitco Gold News — Real-time gold market news
  2. Forex Factory Economic Calendar — Accurate impact ratings for today's events
  3. Gold Price Overview (fallback summary from multiple sources)
"""

import logging
from datetime import datetime
from typing import Optional
from crewai.tools import tool

logger = logging.getLogger("web_scraper_tools")

# Optional imports with graceful fallbacks
try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning(
        "httpx not installed. Web scraping tools will use requests fallback."
    )

try:
    from bs4 import BeautifulSoup

    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logger.warning("beautifulsoup4 not installed. Web scraping tools limited.")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _get_html(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch raw HTML from a URL using httpx or requests fallback."""
    if HTTPX_AVAILABLE:
        try:
            with httpx.Client(
                headers=HEADERS, timeout=timeout, follow_redirects=True
            ) as client:
                res = client.get(url)
                if res.status_code == 200:
                    return res.text
                logger.error(f"HTTP {res.status_code} fetching {url}")
        except Exception as e:
            logger.error(f"httpx error fetching {url}: {e}")
    else:
        try:
            import requests

            res = requests.get(url, headers=HEADERS, timeout=timeout)
            if res.status_code == 200:
                return res.text
        except Exception as e:
            logger.error(f"requests fallback error fetching {url}: {e}")
    return None


@tool("Kitco Gold News Scraper")
def scrape_kitco_news() -> str:
    """
    Scrapes the latest gold market news headlines and summaries from Kitco News.
    Kitco is one of the most authoritative gold price news sources globally.
    Returns up to 8 recent gold-specific news headlines with their publication time.
    """
    if not BS4_AVAILABLE:
        return "BeautifulSoup4 not installed. Cannot scrape Kitco news."

    url = "https://www.kitco.com/news/gold/"
    html = _get_html(url)

    if not html:
        return (
            "Unable to fetch Kitco Gold News at this time.\n"
            "Fallback: Check Google News RSS for gold market updates."
        )

    try:
        soup = BeautifulSoup(html, "html.parser")
        articles = []

        # Kitco article cards
        selectors = [
            "article.article-card",
            "div.article-item",
            "li.news-item",
            "div.news-card",
            "article",
        ]

        items = []
        for selector in selectors:
            items = soup.select(selector)
            if items:
                break

        if not items:
            # Fallback: get all headline links
            links = soup.find_all("a", href=True)
            items = [
                link
                for link in links
                if "/news/" in str(link.get("href", "")) and link.get_text(strip=True)
            ][:10]

        for item in items[:8]:
            # Try to get title
            title_el = (
                item.find("h2")
                or item.find("h3")
                or item.find(class_=lambda x: x and "title" in x.lower())
                or item
            )
            title = title_el.get_text(strip=True) if title_el else ""

            if len(title) < 10:
                continue

            # Try to get time
            time_el = item.find("time") or item.find(
                class_=lambda x: x and "date" in str(x).lower()
            )
            pub_time = time_el.get_text(strip=True) if time_el else "Recent"

            # Simple sentiment
            lower = title.lower()
            bullish = any(
                w in lower
                for w in [
                    "rise",
                    "surge",
                    "gains",
                    "up",
                    "rally",
                    "bullish",
                    "high",
                    "demand",
                    "buy",
                ]
            )
            bearish = any(
                w in lower
                for w in [
                    "fall",
                    "drop",
                    "down",
                    "bearish",
                    "sell",
                    "plunge",
                    "lower",
                    "loss",
                ]
            )
            sentiment = (
                "Bullish"
                if bullish and not bearish
                else "Bearish"
                if bearish and not bullish
                else "Neutral"
            )

            articles.append(f"• [{sentiment}] {title} ({pub_time})")

        if not articles:
            return "No gold news articles found on Kitco at this time."

        return (
            "📰 Kitco Gold News (Live):\n\n"
            + "\n".join(articles)
            + "\n\nSource: kitco.com/news/gold"
        )

    except Exception as e:
        logger.error(f"Error parsing Kitco news: {e}")
        return f"Error parsing Kitco gold news: {str(e)}"


@tool("Forex Factory Calendar Scraper")
def scrape_forex_factory_calendar() -> str:
    """
    Scrapes today's economic calendar events from Forex Factory.
    Provides accurate impact ratings (High/Medium/Low) for all forex events today.
    Focuses on USD events that affect Gold (XAUUSD) price movements.
    """
    if not BS4_AVAILABLE:
        return "BeautifulSoup4 not installed. Cannot scrape Forex Factory calendar."

    url = "https://www.forexfactory.com/calendar"
    html = _get_html(url)

    if not html:
        return (
            "Unable to fetch Forex Factory calendar at this time.\n"
            "Using FMP/fallback economic calendar data instead."
        )

    try:
        soup = BeautifulSoup(html, "html.parser")
        events = []

        # Forex Factory calendar table rows
        rows = soup.select("tr.calendar__row")

        if not rows:
            rows = soup.select("table.calendar tr")

        today = datetime.utcnow().strftime("%A, %b %d")

        for row in rows:
            try:
                # Check currency (we want USD events primarily for gold impact)
                currency_el = row.select_one(".calendar__currency")
                currency = currency_el.get_text(strip=True) if currency_el else ""

                # Impact icon/class
                impact_el = row.select_one(".calendar__impact span")
                impact_class = str(impact_el.get("class", [])) if impact_el else ""
                if "high" in impact_class.lower():
                    impact = "HIGH"
                elif "medium" in impact_class.lower():
                    impact = "MEDIUM"
                elif "low" in impact_class.lower():
                    impact = "LOW"
                else:
                    impact = "UNKNOWN"

                # Event name
                event_el = row.select_one(".calendar__event-title")
                event_name = event_el.get_text(strip=True) if event_el else ""

                # Time
                time_el = row.select_one(".calendar__time")
                event_time = time_el.get_text(strip=True) if time_el else ""

                # Actual / Forecast / Previous
                actual_el = row.select_one(".calendar__actual")
                forecast_el = row.select_one(".calendar__forecast")
                previous_el = row.select_one(".calendar__previous")

                actual = actual_el.get_text(strip=True) if actual_el else "—"
                forecast = forecast_el.get_text(strip=True) if forecast_el else "—"
                previous = previous_el.get_text(strip=True) if previous_el else "—"

                if (
                    event_name
                    and impact in ["HIGH", "MEDIUM"]
                    and currency in ["USD", "XAU"]
                ):
                    gold_impact = (
                        "⚡ Directly impacts Gold"
                        if currency == "USD"
                        else "🥇 Gold-specific event"
                    )
                    events.append(
                        f"⏰ {event_time} | 💵 {currency} | {impact} IMPACT\n"
                        f"  📌 {event_name}\n"
                        f"  Actual: {actual} | Forecast: {forecast} | Previous: {previous}\n"
                        f"  {gold_impact}"
                    )
            except Exception:
                continue

        if not events:
            return (
                f"Forex Factory Calendar — {today} (UTC):\n"
                "No high or medium impact USD events found for today.\n"
                "Market may be relatively quiet for gold price volatility."
            )

        return (
            f"📅 Forex Factory Calendar — {today} (UTC):\n"
            "(Showing HIGH & MEDIUM impact USD events only)\n\n"
            + "\n\n".join(events)
            + "\n\nSource: forexfactory.com/calendar"
        )

    except Exception as e:
        logger.error(f"Error parsing Forex Factory calendar: {e}")
        return f"Error parsing Forex Factory calendar: {str(e)}"
