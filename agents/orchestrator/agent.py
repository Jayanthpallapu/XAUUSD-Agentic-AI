import logging
from typing import Dict, Any
from crewai import Agent, Task, Crew, Process, LLM
from config import settings
from governance.audit.supabase_client import db_service
from api.schemas.models import (
    CorrelationReport,
    GoldNewsReport,
    TradeSignal,
    QAReport,
    PerformanceReport,
    SupervisorReport,
)

# Hermes persistent memory — replaces static lessons backstory
from hermes.memory_store import hermes_memory

# Import tools using absolute project imports
from tools.definitions.market_data import (
    fetch_gold_price,
    fetch_forex_prices,
    fetch_commodities_prices,
    fetch_crypto_prices,
    fetch_market_indices,
    fetch_treasury_yields,
)
from tools.definitions.news_calendar import (
    fetch_news_rss,
    analyze_news_sentiment,
    fetch_economic_calendar,
)
from tools.definitions.trading_performance import (
    execute_paper_trade,
    fetch_trade_performance,
    record_teacher_feedback,
)
from tools.definitions.system import (
    check_agent_health,
    restart_agent_node,
    send_telegram_notification,
)

# Hermes-enhanced web scraping tools (httpx + BeautifulSoup)
from tools.definitions.web_scraper import (
    scrape_kitco_news,
    scrape_forex_factory_calendar,
)

import time
import requests

logger = logging.getLogger("crew_setup")

_cached_llm = None
_cached_llm_time = 0


def verify_llm_tool_support(api_key: str, model: str, base_url: str) -> bool:
    """
    Verifies if the API key is valid, model exists, and supports tool use on the provider.
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # Strip provider prefix if present for direct api call
    api_model = model
    if "/" in model:
        parts = model.split("/")
        if parts[0] in ["openrouter", "groq"]:
            api_model = "/".join(parts[1:])

    # We send a minimal tool call payload to check for 403 (limit exceeded) or 404 (tool support not found)
    data = {
        "model": api_model,
        "messages": [{"role": "user", "content": "ping"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "ping_tool",
                    "description": "ping tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        "max_tokens": 5,
    }

    try:
        res = requests.post(url, headers=headers, json=data, timeout=8)
        if res.status_code == 200:
            res_json = res.json()
            if "error" not in res_json:
                return True
            else:
                logger.warning(
                    f"LLM Verification failed for {model}: {res_json['error']}"
                )
        elif res.status_code == 400:
            # HTTP 400 means the endpoint is reachable, key is active, and tool use is supported
            # (but our minimal verification tool schema/payload format was rejected).
            return True
        else:
            logger.warning(
                f"LLM Verification failed for {model} with status {res.status_code}: {res.text}"
            )
    except Exception as e:
        logger.warning(f"LLM Verification connection failed for {model}: {e}")
    return False


def get_llm(model_name: str = None) -> LLM:
    """
    Returns the best available LLM with Hermes 3 via OpenRouter as primary.
    Failover chain: OpenRouter Hermes 3 → Groq LLaMA-3.3-70B → Groq LLaMA-3.1-8B

    Hermes 3 (NousResearch) is specifically optimized for:
    - Advanced function calling & structured JSON outputs
    - Long-context retention across multi-step agent chains
    - Financial analysis and tool-use reasoning
    """
    global _cached_llm, _cached_llm_time

    current_time = time.time()
    # Cache the chosen LLM for 1 hour to prevent excessive validation requests
    if _cached_llm and (current_time - _cached_llm_time < 3600):
        return _cached_llm

    # Primary: Hermes 3 via OpenRouter
    if settings.OPENROUTER_API_KEY:
        hermes_model = "openrouter/nousresearch/hermes-3-llama-3.1-405b"
        logger.info(f"LLM: Verifying OpenRouter tool support for {hermes_model}...")
        if verify_llm_tool_support(
            settings.OPENROUTER_API_KEY, hermes_model, "https://openrouter.ai/api/v1"
        ):
            try:
                llm = LLM(
                    model=hermes_model,
                    api_key=settings.OPENROUTER_API_KEY,
                    base_url="https://openrouter.ai/api/v1",
                    temperature=0.15,
                )
                logger.info("LLM: Using Hermes 3 405B via OpenRouter (primary).")
                _cached_llm = llm
                _cached_llm_time = current_time
                return llm
            except Exception as e:
                logger.warning(f"OpenRouter LLM creation failed: {e}")
        else:
            logger.warning(
                "OpenRouter Hermes 3 failed verification (likely daily limit or no tool-use endpoints). Falling back to Groq."
            )

    # Secondary failover: Groq LLaMA-3.3-70B
    if settings.GROQ_API_KEY:
        groq_model = "groq/llama-3.3-70b-versatile"
        logger.info(f"LLM: Verifying Groq tool support for {groq_model}...")
        if verify_llm_tool_support(
            settings.GROQ_API_KEY, groq_model, "https://api.groq.com/openai/v1"
        ):
            try:
                llm = LLM(
                    model=groq_model,
                    api_key=settings.GROQ_API_KEY,
                    temperature=0.2,
                )
                logger.info("LLM: Using Groq LLaMA-3.3-70B (failover).")
                _cached_llm = llm
                _cached_llm_time = current_time
                return llm
            except Exception as e:
                logger.error(f"Groq LLM creation failed: {e}")
        else:
            logger.warning("Groq LLaMA-3.3-70B failed verification. Trying fallback.")

    # Final fallback: Groq lightweight model
    logger.warning("LLM: Using Groq LLaMA-3.1-8B-Instant (emergency fallback).")
    llm = LLM(
        model="groq/llama-3.1-8b-instant",
        api_key=settings.GROQ_API_KEY or "gsk_mock_key_for_offline_runs",
    )
    _cached_llm = llm
    _cached_llm_time = current_time
    return llm


def fetch_lessons_backstory(agent_name: str) -> str:
    """
    Retrieves agent lessons from Hermes persistent memory (SQLite).
    Falls back to Supabase DB lessons if memory store is empty.

    Hermes memory grows automatically after every cycle — agents
    accumulate knowledge indefinitely and recall it on every run.
    """
    # Primary: Hermes persistent memory (SQLite — grows with every cycle)
    memory_lessons = hermes_memory.get_lessons(agent_name, k=5)
    if memory_lessons:
        lesson_count = hermes_memory.get_lesson_count(agent_name)
        logger.info(f"Loaded {lesson_count} Hermes memory lessons for {agent_name}.")
        return memory_lessons

    # Fallback: Supabase DB lessons (static, from initial setup)
    try:
        res = db_service.select("agent_registry", {"name": agent_name})
        if res:
            agent = res[0]
            lessons = agent.get("lessons_learned", [])
            if lessons and isinstance(lessons, list):
                formatted = "\nCRITICAL LESSONS LEARNED FROM PAST MISTAKES (You MUST avoid repeating these):\n"
                for idx, item in enumerate(lessons[-5:]):
                    formatted += f"Lesson {idx + 1}:\n- Past Mistake: {item.get('mistake')}\n- Corrective Action: {item.get('correction')}\n- Teacher Lesson: {item.get('lesson')}\n"
                return formatted
    except Exception as e:
        logger.error(f"Error fetching Supabase lessons backstory for {agent_name}: {e}")
    return ""


def create_correlation_agent(llm: LLM) -> Agent:
    lessons = fetch_lessons_backstory("CorrelationAgent")
    return Agent(
        role="Correlated Pairs & News Analyst",
        goal="Analyze prices and financial news of correlated instruments to determine their net impact on Gold price (XAUUSD).",
        backstory=(
            "You are a Senior Quantitative Analyst specializing in macro correlations. You analyze DXY, EURUSD, US10Y yields, "
            "Bitcoin, VIX, Silver, Oil, Copper, and S&P500 to evaluate if macro trends are net bullish or bearish for Gold. "
            "You calculate correlation alignments and support decisions with data."
            f"{lessons}"
        ),
        tools=[
            fetch_forex_prices,
            fetch_commodities_prices,
            fetch_crypto_prices,
            fetch_market_indices,
            fetch_treasury_yields,
            fetch_news_rss,
            scrape_kitco_news,  # Hermes: Live Kitco gold news scraping
        ],
        llm=llm,
        allow_delegation=False,
        max_iter=15,
        verbose=True,
    )


def create_news_agent(llm: LLM) -> Agent:
    lessons = fetch_lessons_backstory("NewsAgent")
    return Agent(
        role="XAUUSD News & Impact Analyst",
        goal="Scrape and analyze gold spot news, federal speeches, geopolitical events, and economic announcements to gauge gold market sentiment.",
        backstory=(
            "You are a veteran Financial Journalist and Market Sentiment Specialist. You monitor breaking geopolitical events, central bank announcements, "
            "CPI inflation releases, and FOMC speeches. You understand how gold price volatility flows back to impact other correlated pairs."
            f"{lessons}"
        ),
        tools=[
            fetch_gold_price,
            fetch_news_rss,
            analyze_news_sentiment,
            fetch_economic_calendar,
            scrape_kitco_news,  # Hermes: Live Kitco gold news
            scrape_forex_factory_calendar,  # Hermes: Live Forex Factory impact ratings
        ],
        llm=llm,
        allow_delegation=False,
        max_iter=15,
        verbose=True,
    )


def create_trading_agent(llm: LLM) -> Agent:
    lessons = fetch_lessons_backstory("TradingAgent")
    return Agent(
        role="Price Reaction Observer & Signal Generator",
        goal="Observe how the spot price of Gold is reacting to the compiled news and correlation alignments, and execute simulated paper trades.",
        backstory=(
            "You are an Elite Commodity Trader. You receive fundamental correlation sheets and news sentiment reports, watch the live spot price of Gold (XAUUSD), "
            "and identify technical entries. You place simulated paper trades (BUY, SELL, or HOLD) with exact entry, stop loss, and take profit levels. "
            "Your trade rules require a risk/reward ratio of at least 1:1.5 and careful risk control based on a starting capital of $10,000 USD."
            f"{lessons}"
        ),
        tools=[fetch_gold_price, execute_paper_trade],
        llm=llm,
        allow_delegation=False,
        max_iter=15,
        verbose=True,
    )


def create_qa_agent(llm: LLM) -> Agent:
    lessons = fetch_lessons_backstory("QAAgent")
    return Agent(
        role="Quality Assurance & Improvement Analyst",
        goal="Audit and review the research data, news analysis, and trading signals to ensure logical consistency, correct inputs, and identify improvements.",
        backstory=(
            "You are a strict Risk Manager and Quality Auditor. You inspect the output of the researchers and the trading agent. "
            "You verify that the trading agent's entries, stop losses, and take profits align with the direction (e.g. SL is below entry for BUY) "
            "and make logical sense given the news sentiment. You flag errors, adjust confidence levels, and list improvement suggestions."
            f"{lessons}"
        ),
        tools=[fetch_gold_price],
        llm=llm,
        allow_delegation=False,
        max_iter=15,
        verbose=True,
    )


def create_performance_agent(llm: LLM) -> Agent:
    lessons = fetch_lessons_backstory("PerformanceAgent")
    return Agent(
        role="Trade Observability & Accuracy Tracker",
        goal="Observe closed trade results, maintain performance records, compile profit metrics, and score the accuracy of all worker agents.",
        backstory=(
            "You are a Trading Desk Performance Controller. You calculate performance metrics like win rate, drawdowns, profit factor, "
            "and overall portfolio health. You track the accuracy of signals over time and help identify which agents are making logical mistakes."
            f"{lessons}"
        ),
        tools=[fetch_trade_performance],
        llm=llm,
        allow_delegation=False,
        max_iter=15,
        verbose=True,
    )


def create_supervisor_agent(llm: LLM) -> Agent:
    lessons = fetch_lessons_backstory("SupervisorAgent")
    return Agent(
        role="Chief AI Officer — System Supervisor",
        goal="Oversee the entire Crew, check agent health logs, diagnose stuck node systems, apply constructive teaching feedback, and notify Telegram.",
        backstory=(
            "You are the Head Supervisor Agent, equipped with LLM reasoning. You check agent health monitors and restart any nodes in error state. "
            "You audit trades and write constructive teacher feedback to guide agents to improve. "
            "You compile the daily execution report and publish notifications to the Telegram channel."
            f"{lessons}"
        ),
        tools=[
            check_agent_health,
            restart_agent_node,
            record_teacher_feedback,
            fetch_trade_performance,
            send_telegram_notification,
        ],
        llm=llm,
        allow_delegation=True,
        max_iter=15,
        verbose=True,
    )


def create_market_crew_flow(cycle_id: str) -> Dict[str, Any]:
    llm = get_llm()

    corr_agent = create_correlation_agent(llm)
    news_agent = create_news_agent(llm)
    trade_agent = create_trading_agent(llm)
    qa_agent = create_qa_agent(llm)
    perf_agent = create_performance_agent(llm)
    supervisor_agent = create_supervisor_agent(llm)

    corr_task = Task(
        description="Fetch forex prices, index prices, crypto rates, commodity rates, and treasury yields. Research how correlated markets are moving. Analyze recent correlated news RSS.",
        expected_output="A structured report evaluating correlation alignment metrics.",
        agent=corr_agent,
        output_pydantic=CorrelationReport,
    )

    news_task = Task(
        description="Fetch gold spot price, search news RSS for gold market sentiment and economic calendar events. Summarize sentiment and note if any high-impact event (CPI, NFP, GDP, Interest rates) is released today.",
        expected_output="A structured gold news and economic event impact analysis.",
        agent=news_agent,
        output_pydantic=GoldNewsReport,
    )

    research_crew = Crew(
        agents=[corr_agent, news_agent],
        tasks=[corr_task, news_task],
        process=Process.sequential,
        verbose=True,
    )

    logger.info("Starting Research Crew kickoff...")
    research_results = research_crew.kickoff()

    corr_output = research_results.tasks_output[0].pydantic
    news_output = research_results.tasks_output[1].pydantic

    db_service.insert(
        "correlation_reports",
        {
            "cycle_id": cycle_id,
            "pair_correlations": [p.dict() for p in corr_output.pair_correlations],
            "news_impacts": [n.dict() for n in corr_output.news_impacts],
            "overall_confluence_score": corr_output.overall_confluence_score,
            "summary": corr_output.summary,
        },
    )
    db_service.update_agent_status("CorrelationAgent", "active", tasks_delta=1)

    db_service.insert(
        "gold_news_reports",
        {
            "cycle_id": cycle_id,
            "news_items": [n.dict() for n in news_output.news_items],
            "market_sentiment": news_output.market_sentiment,
            "impact_on_pairs": [p.dict() for p in news_output.impact_on_pairs],
            "is_high_impact": news_output.is_high_impact,
            "summary": news_output.summary,
        },
    )
    db_service.update_agent_status("NewsAgent", "active", tasks_delta=1)

    trade_task = Task(
        description=(
            f"Observe the current gold price. Using the Correlation Report: {corr_output.summary} "
            f"and the Gold News Report: {news_output.summary}, determine if a BUY or SELL setup exists. "
            f"If conditions are mixed or unclear, select HOLD. If placing a trade, call the Paper Trade Executor tool "
            f"with appropriate SL, TP, entry price, and confidence score. Use cycle_id: {cycle_id}."
        ),
        expected_output="A structured BUY/SELL/HOLD trade signal recommendation.",
        agent=trade_agent,
        output_pydantic=TradeSignal,
    )

    qa_task = Task(
        description=(
            "Review the research findings, news analysis, and the resulting Trade Signal. "
            "Audit the trade levels: make sure SL is below entry for BUY, TP is above entry for BUY, etc. "
            "Adjust the trade signal's confidence score if you find logical mistakes or warning signs. "
            "Write specific actionable improvement suggestions for the agents if they made mistakes."
        ),
        expected_output="A detailed QA audit report approving, rejecting, or adjusting the signal.",
        agent=qa_agent,
        output_pydantic=QAReport,
    )

    analysis_crew = Crew(
        agents=[trade_agent, qa_agent],
        tasks=[trade_task, qa_task],
        process=Process.sequential,
        verbose=True,
    )

    logger.info("Starting Analysis Crew kickoff...")
    analysis_results = analysis_crew.kickoff()

    trade_output = analysis_results.tasks_output[0].pydantic
    qa_output = analysis_results.tasks_output[1].pydantic

    db_service.insert(
        "qa_reports",
        {
            "cycle_id": cycle_id,
            "issues_found": [i.dict() for i in qa_output.issues_found],
            "improvements": [imp.dict() for imp in qa_output.improvements],
            "approval_status": qa_output.approval_status,
            "confidence_adjustment": qa_output.confidence_adjustment,
            "summary": qa_output.summary,
        },
    )
    db_service.update_agent_status("TradingAgent", "active", tasks_delta=1)
    db_service.update_agent_status("QAAgent", "active", tasks_delta=1)

    if qa_output.approval_status == "rejected":
        signals = db_service.select("trade_signals", {"cycle_id": cycle_id})
        if signals:
            db_service.update(
                "trade_signals", {"id": signals[0]["id"]}, {"status": "expired"}
            )
            logger.info(
                f"QA Agent rejected trade signal. Trade ID {signals[0]['id'][:8]} marked as expired/rejected."
            )

    perf_task = Task(
        description="Analyze closed trade results using the Trade Performance Fetcher tool. Compile portfolio statistics (win rate, total PnL, drawdowns, Sharpe) and assess current agent performance scores.",
        expected_output="A compiled portfolio performance and accuracy scorecard.",
        agent=perf_agent,
        output_pydantic=PerformanceReport,
    )

    perf_crew = Crew(
        agents=[perf_agent], tasks=[perf_task], process=Process.sequential, verbose=True
    )

    logger.info("Starting Performance Crew kickoff...")
    perf_results = perf_crew.kickoff()
    perf_output = perf_results.tasks_output[0].pydantic

    db_service.insert(
        "performance_reports",
        {
            "cycle_id": cycle_id,
            "win_rate": perf_output.win_rate,
            "total_pnl": perf_output.total_pnl,
            "sharpe_ratio": perf_output.sharpe_ratio,
            "max_drawdown": perf_output.max_drawdown,
            "profit_factor": perf_output.profit_factor,
            "total_trades": perf_output.total_trades,
            "winning_trades": perf_output.winning_trades,
            "losing_trades": perf_output.losing_trades,
            "agent_scores": perf_output.agent_scores,
        },
    )
    db_service.update_agent_status("PerformanceAgent", "active", tasks_delta=1)

    supervisor_task = Task(
        description=(
            "Run the Agent Health Monitor tool to diagnose node health. If any node has high error counts, "
            "call the Agent Node Restarter. Write teacher feedback notes for the trading agent if any trades "
            "underperformed or failed QA validation, and use the Teacher Feedback Recorder to submit them. "
            "Draft a comprehensive daily execution summary, and call the Telegram Notifier tool to send it."
        ),
        expected_output="A summary of supervisor actions taken and system health.",
        agent=supervisor_agent,
        output_pydantic=SupervisorReport,
    )

    supervisor_crew = Crew(
        agents=[supervisor_agent],
        tasks=[supervisor_task],
        process=Process.sequential,
        verbose=True,
    )

    logger.info("Starting Supervisor Crew kickoff...")
    supervisor_results = supervisor_crew.kickoff()
    supervisor_output = supervisor_results.tasks_output[0].pydantic

    db_service.insert(
        "supervisor_reports",
        {
            "cycle_id": cycle_id,
            "agent_statuses": [a.dict() for a in supervisor_output.agent_statuses],
            "actions_taken": [a.dict() for a in supervisor_output.actions_taken],
            "daily_summary": supervisor_output.daily_summary,
            "telegram_sent": supervisor_output.telegram_sent,
        },
    )
    db_service.update_agent_status("SupervisorAgent", "active", tasks_delta=1)

    return {
        "correlation": corr_output.dict(),
        "news": news_output.dict(),
        "trade": trade_output.dict(),
        "qa": qa_output.dict(),
        "performance": perf_output.dict(),
        "supervisor": supervisor_output.dict(),
    }
