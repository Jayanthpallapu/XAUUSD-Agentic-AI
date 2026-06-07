import logging
import requests
import feedparser
from datetime import datetime
from crewai.tools import tool
from config import settings

logger = logging.getLogger("news_calendar_tools")


@tool("Google News Fetcher")
def fetch_news_rss(query: str = "gold price XAUUSD forex") -> str:
    """
    Fetches the latest financial news related to a query from Google News RSS.
    Query can be specific, e.g., 'gold CPI FOMC market sentiment'.
    """
    formatted_query = query.replace(" ", "+")
    rss_url = f"https://news.google.com/rss/search?q={formatted_query}&hl=en-US&gl=US&ceid=US:en"

    try:
        feed = feedparser.parse(rss_url)
        entries = feed.entries[:8]

        if not entries:
            return f"No news found on Google News RSS for query: {query}"

        items = []
        for i, entry in enumerate(entries):
            title = entry.title
            published = entry.published
            source = entry.source.get("title", "Google News")
            link = entry.link

            sentiment = "Neutral"
            lower_title = title.lower()
            bullish_words = [
                "rise",
                "surge",
                "gain",
                "higher",
                "bullish",
                "buying",
                "rally",
                "strengthens",
                "inflation",
                "cut",
                "up",
            ]
            bearish_words = [
                "fall",
                "plummet",
                "loss",
                "lower",
                "bearish",
                "selling",
                "slump",
                "drops",
                "strengthen",
                "hike",
                "down",
            ]

            bull_count = sum(1 for w in bullish_words if w in lower_title)
            bear_count = sum(1 for w in bearish_words if w in lower_title)

            if bull_count > bear_count:
                sentiment = "Bullish"
            elif bear_count > bull_count:
                sentiment = "Bearish"

            items.append(
                f"{i + 1}. [{source}] {title}\n"
                f"   Published: {published}\n"
                f"   Estimated Local Sentiment: {sentiment}\n"
                f"   Link: {link}"
            )

        return f"Latest News for '{query}':\n\n" + "\n\n".join(items)

    except Exception as e:
        logger.error(f"Error fetching RSS news: {e}")
        return f"Error reading news RSS: {str(e)}. Fallback: Fed speech creates high volatility; Gold spot prices trading sideways."


@tool("News Sentiment Analyzer")
def analyze_news_sentiment() -> str:
    """
    Fetches official news sentiment statistics from Alpha Vantage (if key configured) or calculates a local summary.
    Returns market sentiment score between -1.0 (extremely bearish) to +1.0 (extremely bullish) and key insights.
    """
    if settings.ALPHA_VANTAGE_API_KEY:
        try:
            url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers=CRYPTO:BTC,FOREX:USD&apikey={settings.ALPHA_VANTAGE_API_KEY}"
            res = requests.get(url, timeout=10)
            data = res.json()
            feed = data.get("feed", [])

            if feed:
                sentiment_sum = 0.0
                bullish_count = 0
                bearish_count = 0
                headlines = []

                for item in feed[:5]:
                    score = float(item.get("overall_sentiment_score", 0.0))
                    sentiment_sum += score
                    label = item.get("overall_sentiment_label", "Neutral")

                    if "Bullish" in label:
                        bullish_count += 1
                    elif "Bearish" in label:
                        bearish_count += 1

                    headlines.append(
                        f"- {item.get('title')} (Sentiment: {label}, Score: {score:.2f})"
                    )

                avg_sentiment = sentiment_sum / len(feed[:5])
                overall_lbl = (
                    "Bullish"
                    if avg_sentiment > 0.15
                    else "Bearish"
                    if avg_sentiment < -0.15
                    else "Neutral"
                )

                return (
                    f"Overall Market Sentiment: {overall_lbl} (Average Score: {avg_sentiment:.2f})\n"
                    f"Bullish Articles: {bullish_count}, Bearish Articles: {bearish_count}\n"
                    f"Recent Headlines:\n" + "\n".join(headlines)
                )
        except Exception as e:
            logger.error(f"Alpha Vantage news sentiment failed: {e}")

    try:
        feed = feedparser.parse(
            "https://news.google.com/rss/search?q=gold+price+forex&hl=en-US"
        )
        entries = feed.entries[:5]

        bullish_indicators = 0
        bearish_indicators = 0
        headlines = []

        for entry in entries:
            title = entry.title
            lower_title = title.lower()

            bull_words = [
                "rise",
                "high",
                "rally",
                "gain",
                "inflation",
                "cuts",
                "geopolitical",
                "risk",
                "war",
                "tensions",
                "buying",
            ]
            bear_words = [
                "fall",
                "drop",
                "hike",
                "stronger dollar",
                "yields rise",
                "selling",
                "plummets",
                "slump",
            ]

            bull = sum(1 for w in bull_words if w in lower_title)
            bear = sum(1 for w in bear_words if w in lower_title)

            label = "Neutral"
            if bull > bear:
                bullish_indicators += 1
                label = "Somewhat Bullish"
            elif bear > bull:
                bearish_indicators += 1
                label = "Somewhat Bearish"

            headlines.append(f"- {title} ({label})")

        net_score = (bullish_indicators - bearish_indicators) / max(1, len(entries))
        overall = (
            "Bullish"
            if net_score > 0.1
            else "Bearish"
            if net_score < -0.1
            else "Neutral"
        )

        return (
            f"Local RSS Sentiment Analysis:\n"
            f"Overall Sentiment: {overall} (Net Index Score: {net_score:.2f})\n"
            f"Bullish indicators detected: {bullish_indicators}\n"
            f"Bearish indicators detected: {bearish_indicators}\n"
            f"Recent Google News Headlines parsed:\n" + "\n".join(headlines)
        )
    except Exception as e:
        logger.error(f"Local RSS sentiment calculation failed: {e}")

    return (
        "Market Sentiment Report (Mocked due to failures):\n"
        "Overall Sentiment: Somewhat Bullish (Score: 0.25)\n"
        "Reason: Continued geopolitical risk in Eastern Europe and expectations of FOMC easing rate path, despite slightly stronger US dollar."
    )


@tool("Economic Calendar Fetcher")
def fetch_economic_calendar() -> str:
    """
    Fetches the economic calendar events for the day or week, highlighting high-impact events
    like FOMC rate decisions, Non-Farm Payrolls (NFP), CPI, GDP releases, and speech events.
    """
    if settings.FMP_API_KEY:
        try:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            url = f"https://financialmodelingprep.com/api/v3/economic_calendar?from={today}&to={today}&apikey={settings.FMP_API_KEY}"
            res = requests.get(url, timeout=10)
            data = res.json()

            if isinstance(data, list) and len(data) > 0:
                events = []
                for ev in data[:10]:
                    impact = ev.get("impact", "Low")
                    if impact in ["Medium", "High"]:
                        events.append(
                            f"- Event: {ev.get('event')}\n"
                            f"  Country: {ev.get('country')}\n"
                            f"  Time: {ev.get('date')}\n"
                            f"  Actual: {ev.get('actual') or 'N/A'} | Estimate: {ev.get('estimate') or 'N/A'} | Previous: {ev.get('previous') or 'N/A'}\n"
                            f"  Impact Rating: {impact}"
                        )
                if events:
                    return "Today's Key Economic Events:\n\n" + "\n\n".join(events)
        except Exception as e:
            logger.error(f"FMP calendar API failed: {e}")

    weekday = datetime.utcnow().weekday()
    days = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    day_name = days[weekday]

    events_by_day = {
        "Monday": [
            {
                "event": "US ISM Manufacturing PMI",
                "impact": "High",
                "time": "14:00 UTC",
                "est": "48.2",
                "prev": "47.8",
            },
            {
                "event": "EUR ECB President Lagarde Speech",
                "impact": "Medium",
                "time": "15:30 UTC",
                "est": "N/A",
                "prev": "N/A",
            },
        ],
        "Tuesday": [
            {
                "event": "US JOLTs Job Openings",
                "impact": "High",
                "time": "14:00 UTC",
                "est": "8.10M",
                "prev": "8.06M",
            },
            {
                "event": "AUD RBA Interest Rate Decision",
                "impact": "High",
                "time": "04:30 UTC",
                "est": "4.35%",
                "prev": "4.35%",
            },
        ],
        "Wednesday": [
            {
                "event": "US ADP Non-Farm Employment Change",
                "impact": "High",
                "time": "12:15 UTC",
                "est": "150K",
                "prev": "152K",
            },
            {
                "event": "US ISM Services PMI",
                "impact": "High",
                "time": "14:00 UTC",
                "est": "50.8",
                "prev": "49.4",
            },
            {
                "event": "US FOMC Meeting Minutes",
                "impact": "High",
                "time": "18:00 UTC",
                "est": "N/A",
                "prev": "N/A",
            },
        ],
        "Thursday": [
            {
                "event": "US Unemployment Claims",
                "impact": "High",
                "time": "12:30 UTC",
                "est": "215K",
                "prev": "219K",
            },
            {
                "event": "EUR ECB Interest Rate Decision",
                "impact": "High",
                "time": "12:15 UTC",
                "est": "4.00%",
                "prev": "4.25%",
            },
        ],
        "Friday": [
            {
                "event": "US Non-Farm Payrolls (NFP)",
                "impact": "High",
                "time": "12:30 UTC",
                "est": "180K",
                "prev": "175K",
            },
            {
                "event": "US Unemployment Rate",
                "impact": "High",
                "time": "12:30 UTC",
                "est": "3.9%",
                "prev": "4.0%",
            },
        ],
    }

    events = events_by_day.get(
        day_name,
        [
            {
                "event": "No high-impact economic calendar events scheduled (Weekend)",
                "impact": "Low",
                "time": "N/A",
                "est": "N/A",
                "prev": "N/A",
            }
        ],
    )

    calendar_output = (
        f"Economic Calendar - {day_name} (Simulation based on typical schedules):\n\n"
    )
    for ev in events:
        calendar_output += (
            f"- Event: {ev['event']}\n"
            f"  Time: {ev['time']}\n"
            f"  Impact: {ev['impact']}\n"
            f"  Estimate: {ev['est']} | Previous: {ev['prev']}\n\n"
        )
    return calendar_output
