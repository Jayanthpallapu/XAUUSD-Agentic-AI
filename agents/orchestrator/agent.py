"""
XAUUSD Multi-Agent Pipeline
============================
Hierarchical parallel execution:

Track A - Fundamental Research:
  NewsResearchAgent + CorrelationAgent -> FundamentalDirectionAgent

Track B - Technical Research:
  6 Timeframe Analysts (1W, 1D, 4H, 1H, 15M, 5M) -> TechnicalDirectionAgent

Both tracks run concurrently via ThreadPoolExecutor.
Results converge at QATradeAgent -> TelegramReportAgent -> (human approval via Telegram callback)
"""

import logging
import json
import time
import uuid
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from config import settings
from governance.audit.supabase_client import db_service
from api.schemas.models import (
    NewsResearchOutput,
    CorrelationOutput,
    FundamentalDirectionOutput,
    TechnicalDirectionOutput,
    TimeframeAnalysis,
    QATradeDecision,
)
from hermes.memory_store import hermes_memory
from tools.definitions.market_data import (
    fetch_gold_price,
    fetch_forex_prices,
    fetch_commodities_prices,
    fetch_crypto_prices,
    fetch_market_indices,
    fetch_treasury_yields,
    fetch_finnhub_news,
    fetch_alpha_vantage_sentiment,
)
from tools.definitions.news_calendar import (
    fetch_news_rss,
    analyze_news_sentiment,
    fetch_economic_calendar,
)
from tools.definitions.technical_analysis import fetch_ohlcv_data, analyze_price_structure
from tools.definitions.trading_performance import (
    execute_paper_trade,
    fetch_trade_performance,
    record_teacher_feedback,
)
from tools.definitions.system import (
    check_agent_health,
    restart_agent_node,
    send_telegram_notification,
    send_telegram_trade_signal,
)
from tools.definitions.web_scraper import scrape_kitco_news, scrape_forex_factory_calendar

logger = logging.getLogger("xauusd_pipeline")

_cached_llm = None
_cached_llm_time = 0

ACCOUNT_BALANCE = 10000.0   # Paper trading account balance in USD
MIN_RR_RATIO = 3.0           # Minimum 1:3 risk/reward required
MAX_RISK_PCT = 1.0            # Maximum 1% account risk per trade
TIMEFRAMES = ["1W", "1D", "4H", "1H", "15M", "5M"]


# ─────────────────────────────────────────────
# LLM PROVIDER
# ─────────────────────────────────────────────

def verify_llm_tool_support(api_key: str, model: str, base_url: str) -> bool:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "tools": [{"type": "function", "function": {
            "name": "ping_tool",
            "description": "ping tool",
            "parameters": {"type": "object", "properties": {}},
        }}],
        "max_tokens": 5,
    }
    try:
        res = requests.post(url, headers=headers, json=data, timeout=8)
        if res.status_code in [200, 400]:
            return True
        logger.warning(f"LLM Verification failed for {model}: {res.status_code}")
    except Exception as e:
        logger.warning(f"LLM Verification connection failed for {model}: {e}")
    return False


def get_llm() -> ChatOpenAI:
    """Returns best available LLM. OpenRouter primary, Groq failover."""
    global _cached_llm, _cached_llm_time
    current_time = time.time()
    if _cached_llm and (current_time - _cached_llm_time < 3600):
        return _cached_llm

    if settings.OPENROUTER_API_KEY:
        hermes_model = "nousresearch/hermes-3-llama-3.1-405b"
        if verify_llm_tool_support(settings.OPENROUTER_API_KEY, hermes_model, "https://openrouter.ai/api/v1"):
            try:
                llm = ChatOpenAI(
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

    if settings.GROQ_API_KEY:
        groq_model = "llama-3.3-70b-versatile"
        if verify_llm_tool_support(settings.GROQ_API_KEY, groq_model, "https://api.groq.com/openai/v1"):
            try:
                llm = ChatOpenAI(
                    model=groq_model,
                    api_key=settings.GROQ_API_KEY,
                    base_url="https://api.groq.com/openai/v1",
                    temperature=0.2,
                )
                logger.info("LLM: Using Groq LLaMA-3.3-70B (failover).")
                _cached_llm = llm
                _cached_llm_time = current_time
                return llm
            except Exception as e:
                logger.error(f"Groq LLM creation failed: {e}")

    logger.warning("LLM: Using Groq LLaMA-3.1-8B-Instant (emergency fallback).")
    llm = ChatOpenAI(
        model="llama-3.1-8b-instant",
        api_key=settings.GROQ_API_KEY or "no-key",
        base_url="https://api.groq.com/openai/v1",
        temperature=0.2,
    )
    _cached_llm = llm
    _cached_llm_time = current_time
    return llm


def fetch_lessons_backstory(agent_name: str) -> str:
    """Retrieves memory lessons for an agent to inject into its backstory."""
    memory_lessons = hermes_memory.get_lessons(agent_name, k=5)
    if memory_lessons:
        return memory_lessons
    try:
        res = db_service.select("agent_registry", {"name": agent_name})
        if res:
            lessons = res[0].get("lessons_learned", [])
            if lessons and isinstance(lessons, list):
                formatted = "\nCRITICAL LESSONS LEARNED FROM PAST MISTAKES:\n"
                for idx, item in enumerate(lessons[-5:]):
                    formatted += (
                        f"Lesson {idx + 1}:\n"
                        f"- Past Mistake: {item.get('mistake')}\n"
                        f"- Corrective Action: {item.get('correction')}\n"
                        f"- Key Lesson: {item.get('lesson')}\n"
                    )
                return formatted
    except Exception as e:
        logger.error(f"Error fetching lessons for {agent_name}: {e}")
    return ""


# ─────────────────────────────────────────────
# CORE LANGCHAIN AGENT RUNNER
# ─────────────────────────────────────────────

def run_langchain_agent(
    llm: ChatOpenAI,
    role: str,
    goal: str,
    backstory: str,
    tools: list,
    output_pydantic,
    prompt_content: str,
) -> Any:
    """
    Executes a LangChain agent with tools in a ReAct-style loop,
    then returns a structured Pydantic model output.
    """
    logger.info(f"Agent [{role}]: Starting execution...")
    tool_map = {t.name: t for t in tools} if tools else {}
    llm_with_tools = llm.bind_tools(tools) if tools else llm

    system_prompt = (
        f"You are the {role}.\n"
        f"Goal: {goal}\n"
        f"Backstory: {backstory}\n\n"
        "You have access to helper tools. Use them to gather real-time market data before analysis.\n"
        "CRITICAL: When calling a tool, output ONLY the tool call block. No text before or after the tool call.\n"
        "After gathering all needed data, provide your full analysis."
    )
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=prompt_content)]

    max_steps = 12
    for step in range(1, max_steps + 1):
        logger.info(f"Agent [{role}] Step {step}: Invoking model...")
        response = llm_with_tools.invoke(messages)
        tool_calls = getattr(response, "tool_calls", [])
        if not tool_calls:
            messages.append(response)
            break
        messages.append(response)
        for tc in tool_calls:
            name = tc["name"]
            args = tc["args"]
            tool_id = tc["id"]
            logger.info(f"Agent [{role}] Step {step}: Calling tool '{name}'")
            if name in tool_map:
                try:
                    result = tool_map[name].invoke(args)
                except Exception as e:
                    result = f"Error executing tool '{name}': {e}"
                    logger.error(result)
            else:
                result = f"Error: Tool '{name}' not registered."
                logger.error(result)
            messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))

    logger.info(f"Agent [{role}]: Generating structured output...")
    try:
        llm_structured = llm.with_structured_output(output_pydantic)
        final = llm_structured.invoke(messages + [HumanMessage(
            content=f"Based on all research above, provide your final structured output for {output_pydantic.__name__}."
        )])
    except Exception as e:
        logger.warning(f"Structured output failed ({e}). Falling back to json_mode...")
        schema_str = json.dumps(output_pydantic.model_json_schema(), indent=2)
        llm_structured = llm.with_structured_output(output_pydantic, method="json_mode")
        final = llm_structured.invoke(messages + [HumanMessage(
            content=(
                f"Output a valid JSON object matching this schema:\n\n"
                f"```json\n{schema_str}\n```\n\n"
                "Output ONLY the JSON object starting with '{' and ending with '}'. No extra text."
            )
        )])
    return final


# ─────────────────────────────────────────────
# FUNDAMENTAL RESEARCH TRACK
# ─────────────────────────────────────────────

def run_fundamental_research(llm: ChatOpenAI, cycle_id: str) -> FundamentalDirectionOutput:
    """Runs NewsResearchAgent + CorrelationAgent then synthesizes FundamentalDirectionOutput."""
    logger.info("=== FUNDAMENTAL RESEARCH TRACK STARTED ===")

    # Step 1: News Research Agent
    news_output = run_langchain_agent(
        llm=llm,
        role="NewsResearchAgent",
        goal=(
            "Research and analyze all gold-relevant news, economic events, Fed communications, "
            "inflation data, and geopolitical factors to determine fundamental gold sentiment."
        ),
        backstory=(
            "You are a veteran Financial Journalist and Macro Analyst specializing in Gold markets. "
            "You monitor breaking geopolitical events, central bank announcements, CPI/PPI inflation releases, "
            "FOMC speeches, and Fed fund rate decisions. "
            "Key rule: hawkish Fed = bearish gold, dovish Fed = bullish gold. "
            "Use Finnhub and Alpha Vantage for professional-grade news sentiment."
            + fetch_lessons_backstory("NewsResearchAgent")
        ),
        tools=[
            fetch_gold_price,
            fetch_news_rss,
            analyze_news_sentiment,
            fetch_economic_calendar,
            scrape_kitco_news,
            scrape_forex_factory_calendar,
            fetch_finnhub_news,
            fetch_alpha_vantage_sentiment,
        ],
        output_pydantic=NewsResearchOutput,
        prompt_content=(
            "Complete all steps in order:\n"
            "1. Fetch current gold spot price.\n"
            "2. Fetch news RSS for 'gold FOMC CPI geopolitical'.\n"
            "3. Get official sentiment from Alpha Vantage.\n"
            "4. Get live headlines from Finnhub.\n"
            "5. Scrape Kitco News for latest gold headlines.\n"
            "6. Fetch today's economic calendar events.\n"
            "7. Scrape Forex Factory for high-impact USD events.\n"
            "Synthesize all data into a comprehensive news research report."
        ),
    )
    db_service.update_agent_status("NewsResearchAgent", "active", tasks_delta=1)

    # Step 2: Correlation Agent
    corr_output = run_langchain_agent(
        llm=llm,
        role="CorrelationAgent",
        goal=(
            "Analyze DXY, US10Y yields, commodities, crypto, and equity indices "
            "to determine their combined net impact on Gold (XAUUSD)."
        ),
        backstory=(
            "You are a Senior Quantitative Analyst specializing in macro correlations. "
            "Key rules: DXY rising = bearish gold (inverse correlation). "
            "US10Y yields rising = bearish gold (opportunity cost). "
            "VIX spiking = risk-off = bullish gold (safe haven). "
            "S&P500 falling sharply = flight to safety = bullish gold. "
            "Silver leading gold higher = bullish momentum confirmation. "
            "FRED API provides official yield data. Use it for accuracy."
            + fetch_lessons_backstory("CorrelationAgent")
        ),
        tools=[
            fetch_forex_prices,
            fetch_commodities_prices,
            fetch_crypto_prices,
            fetch_market_indices,
            fetch_treasury_yields,
        ],
        output_pydantic=CorrelationOutput,
        prompt_content=(
            "Complete all steps in order:\n"
            "1. Fetch DXY, EUR/USD, and key forex pairs (EURUSD, USDJPY, GBPUSD).\n"
            "2. Fetch US 10Y and 2Y Treasury yields and calculate yield curve spread.\n"
            "3. Fetch commodity prices: Silver, WTI Oil, Brent, Copper.\n"
            "4. Fetch S&P500 and VIX indices.\n"
            "5. Fetch Bitcoin price (risk sentiment indicator).\n"
            "Analyze correlation scores and calculate net confluence score for gold direction."
        ),
    )
    db_service.update_agent_status("CorrelationAgent", "active", tasks_delta=1)

    # Step 3: Fundamental Direction Agent (synthesizes News + Correlation)
    fundamental_output = run_langchain_agent(
        llm=llm,
        role="FundamentalDirectionAgent",
        goal=(
            "Synthesize news research and correlation analysis into a clear directional bias "
            "(BULLISH, BEARISH, or NEUTRAL) with a confidence score."
        ),
        backstory=(
            "You are the Chief Fundamental Analyst. You receive research from the News Team and Correlation Team. "
            "Weigh the evidence and produce the final fundamental direction. "
            "If news and correlations agree strongly: confidence = 0.7-0.9. "
            "If they partially disagree: confidence = 0.5-0.6, direction = weaker signal. "
            "If they directly contradict: confidence <= 0.4, direction = NEUTRAL. "
            "High-impact events (FOMC, NFP, CPI) are overriding factors."
            + fetch_lessons_backstory("FundamentalDirectionAgent")
        ),
        tools=[],
        output_pydantic=FundamentalDirectionOutput,
        prompt_content=(
            f"News Research Report:\n{json.dumps(news_output.dict(), indent=2)}\n\n"
            f"Correlation Analysis Report:\n{json.dumps(corr_output.dict(), indent=2)}\n\n"
            "Determine the final fundamental direction for XAU/USD. "
            "Weigh all evidence: news sentiment, economic events, correlation alignments. "
            "Identify the top 3-5 key drivers and risk factors."
        ),
    )
    db_service.update_agent_status("FundamentalDirectionAgent", "active", tasks_delta=1)

    db_service.insert("fundamental_reports", {
        "cycle_id": cycle_id,
        "news_summary": news_output.summary,
        "news_sentiment_score": news_output.sentiment_score,
        "is_high_impact_day": news_output.is_high_impact_day,
        "correlation_confluence_score": corr_output.confluence_score,
        "direction": fundamental_output.direction,
        "confidence": fundamental_output.confidence,
        "key_drivers": fundamental_output.key_drivers,
        "risk_factors": fundamental_output.risk_factors,
        "summary": fundamental_output.summary,
    })

    logger.info(
        f"=== FUNDAMENTAL RESEARCH COMPLETE: {fundamental_output.direction} "
        f"(Confidence: {fundamental_output.confidence:.0%}) ==="
    )
    return fundamental_output


# ─────────────────────────────────────────────
# TECHNICAL RESEARCH TRACK
# ─────────────────────────────────────────────

def run_single_timeframe_analyst(llm: ChatOpenAI, timeframe: str) -> TimeframeAnalysis:
    """Runs a single timeframe analyst for the given timeframe."""
    logger.info(f"Technical Analyst [{timeframe}]: Fetching OHLCV data...")
    try:
        ohlcv_json = fetch_ohlcv_data.invoke({"timeframe": timeframe, "bars": 50})
        structure_analysis = analyze_price_structure.invoke({
            "ohlcv_json": ohlcv_json,
            "timeframe": timeframe,
        })

        messages = [
            SystemMessage(content=(
                f"You are a professional Technical Analyst for XAU/USD on the {timeframe} timeframe. "
                "Analyze the provided technical structure and OHLCV data. "
                "CRITICAL: Output ONLY valid JSON — no extra text, no markdown."
            )),
            HumanMessage(content=(
                f"Technical Structure Analysis:\n\n{structure_analysis}\n\n"
                f"OHLCV Data (first 200 chars):\n{ohlcv_json[:200]}...\n\n"
                f"Provide a TimeframeAnalysis with: "
                f"timeframe='{timeframe}', trend (BULLISH/BEARISH/RANGING), "
                "structure, key_support (float), key_resistance (float), "
                "order_block (string or null), liquidity_zone (string or null), "
                "candle_pattern (string or null), analysis (2-3 sentence narrative)."
            )),
        ]
        try:
            result = llm.with_structured_output(TimeframeAnalysis).invoke(messages)
        except Exception as e:
            logger.warning(f"TF [{timeframe}] structured fallback: {e}")
            schema = json.dumps(TimeframeAnalysis.model_json_schema(), indent=2)
            result = llm.with_structured_output(TimeframeAnalysis, method="json_mode").invoke(
                messages + [HumanMessage(content=f"Output ONLY JSON matching:\n```json\n{schema}\n```")]
            )
        logger.info(f"Technical Analyst [{timeframe}]: {result.trend}")
        return result
    except Exception as e:
        logger.error(f"Technical Analyst [{timeframe}] failed: {e}")
        return TimeframeAnalysis(
            timeframe=timeframe,
            trend="RANGING",
            structure="Indeterminate due to data error",
            key_support=2600.0,
            key_resistance=2700.0,
            order_block=None,
            liquidity_zone=None,
            candle_pattern=None,
            analysis=f"Analysis failed for {timeframe}: {str(e)[:100]}",
        )


def run_technical_research(llm: ChatOpenAI, cycle_id: str) -> TechnicalDirectionOutput:
    """Runs all 6 timeframe analysts then synthesizes TechnicalDirectionOutput."""
    logger.info("=== TECHNICAL RESEARCH TRACK STARTED ===")

    timeframe_results = []
    for tf in TIMEFRAMES:
        result = run_single_timeframe_analyst(llm, tf)
        timeframe_results.append(result)
        db_service.update_agent_status(f"Analyst_{tf}", "active", tasks_delta=1)

    timeframe_summaries = "\n\n".join([
        f"{r.timeframe}: {r.trend} | Structure: {r.structure} | "
        f"S: ${r.key_support:.2f} / R: ${r.key_resistance:.2f} | "
        f"OB: {r.order_block or 'None'} | Pattern: {r.candle_pattern or 'None'}"
        for r in timeframe_results
    ])

    tech_output = run_langchain_agent(
        llm=llm,
        role="TechnicalDirectionAgent",
        goal=(
            "Synthesize multi-timeframe analysis into a final technical directional bias "
            "with confidence score, entry zone, and invalidation level."
        ),
        backstory=(
            "You are the Head Technical Analyst. You receive analysis from 6 timeframe analysts. "
            "Principle: Higher timeframe trumps lower timeframe. "
            "1W and 1D establish macro trend. 4H and 1H define intermediate swing. "
            "15M and 5M provide precise entry trigger. "
            "For BULLISH: at least 1D must be bullish, 4H must confirm, 1H/15M show entry setup. "
            "Entry zones: order blocks, support zones, or post-breakout retests. "
            "Invalidation = the structural level that breaks the thesis."
            + fetch_lessons_backstory("TechnicalDirectionAgent")
        ),
        tools=[fetch_gold_price],
        output_pydantic=TechnicalDirectionOutput,
        prompt_content=(
            f"Multi-Timeframe Analysis Results:\n\n{timeframe_summaries}\n\n"
            "Based on the above, determine:\n"
            "1. Overall technical direction (BULLISH, BEARISH, or NEUTRAL)\n"
            "2. Higher timeframe bias (1W+1D combined)\n"
            "3. Lower timeframe entry signal (1H+15M+5M): BUY, SELL, or WAIT\n"
            "4. Optimal entry zone (e.g. '$2635 - $2640')\n"
            "5. Invalidation level (price that breaks the setup)\n"
            "6. Confidence score (0.0-1.0)\n"
            "Include all 6 timeframe_analyses in your output."
        ),
    )
    tech_output.timeframe_analyses = timeframe_results
    db_service.update_agent_status("TechnicalDirectionAgent", "active", tasks_delta=1)

    db_service.insert("technical_reports", {
        "cycle_id": cycle_id,
        "direction": tech_output.direction,
        "confidence": tech_output.confidence,
        "htf_bias": tech_output.htf_bias,
        "ltf_entry_signal": tech_output.ltf_entry_signal,
        "entry_zone": tech_output.entry_zone,
        "invalidation_level": tech_output.invalidation_level,
        "timeframe_count": len(timeframe_results),
        "summary": tech_output.summary,
    })

    logger.info(
        f"=== TECHNICAL RESEARCH COMPLETE: {tech_output.direction} "
        f"(Confidence: {tech_output.confidence:.0%}) ==="
    )
    return tech_output


# ─────────────────────────────────────────────
# QA TRADE AGENT
# ─────────────────────────────────────────────

def run_qa_trade_agent(
    llm: ChatOpenAI,
    cycle_id: str,
    fundamental: FundamentalDirectionOutput,
    technical: TechnicalDirectionOutput,
) -> QATradeDecision:
    """
    Validates confluence, RR >= 1:3, and risk parameters.
    Produces final APPROVED or REJECTED decision with full trade parameters.
    """
    logger.info("=== QA TRADE AGENT STARTED ===")
    gold_price_str = fetch_gold_price.func()
    match = re.search(r"\$(\d+(?:\.\d+)?)\s*USD", gold_price_str)
    current_price = float(match.group(1)) if match else 2645.0

    qa_output = run_langchain_agent(
        llm=llm,
        role="QATradeAgent",
        goal=(
            f"Validate fundamental and technical research to produce a precise, risk-controlled "
            f"trade signal for XAU/USD. "
            f"Rules: (1) Both tracks must agree on direction. "
            f"(2) Minimum RR ratio = {MIN_RR_RATIO}:1. "
            f"(3) Maximum account risk = {MAX_RISK_PCT}% per trade. "
            "(4) Entry must be near key technical structure. "
            "(5) Any rule failure = REJECTED."
        ),
        backstory=(
            "You are the Chief Risk Manager and Trade Validator. You have final authority on all signals. "
            "Your role is capital protection. Rules are non-negotiable. "
            f"Account: ${ACCOUNT_BALANCE:,.0f} USD paper trading. "
            "Lot size formula: (Account * Risk%) / (SL_pips * pip_value). "
            "For Gold spot: pip = $0.10 per 0.01 lot. Standard lot = 100 oz. "
            "Stop Loss: beyond invalidation level or key structure. "
            "Take Profit 1: next major resistance/support at minimum RR 1:3. "
            "If both directions NEUTRAL or disagree: REJECTED."
            + fetch_lessons_backstory("QATradeAgent")
        ),
        tools=[fetch_gold_price],
        output_pydantic=QATradeDecision,
        prompt_content=(
            f"Current XAU/USD Price: ${current_price:.2f}\n\n"
            f"FUNDAMENTAL DIRECTION REPORT:\n"
            f"Direction: {fundamental.direction} | Confidence: {fundamental.confidence:.0%}\n"
            f"Key Drivers: {', '.join(fundamental.key_drivers)}\n"
            f"Risk Factors: {', '.join(fundamental.risk_factors)}\n"
            f"Summary: {fundamental.summary}\n\n"
            f"TECHNICAL DIRECTION REPORT:\n"
            f"Direction: {technical.direction} | Confidence: {technical.confidence:.0%}\n"
            f"HTF Bias: {technical.htf_bias}\n"
            f"LTF Entry Signal: {technical.ltf_entry_signal}\n"
            f"Entry Zone: {technical.entry_zone}\n"
            f"Invalidation Level: ${technical.invalidation_level:.2f}\n"
            f"Summary: {technical.summary}\n\n"
            f"VALIDATION RULES:\n"
            f"1. Both directions must agree (BULLISH+BULLISH or BEARISH+BEARISH). If not: REJECTED.\n"
            f"2. Calculate RR = (|TP1 - Entry|) / (|Entry - SL|). Must be >= {MIN_RR_RATIO}. If not: REJECTED.\n"
            f"3. Lot size = ({ACCOUNT_BALANCE} * {MAX_RISK_PCT / 100}) / (SL_pips * 10). Round to 2 decimals.\n"
            f"4. If combined confidence < 0.50: REJECTED.\n"
            "Calculate entry, SL, TP1, lot size, RR ratio. Validate all rules. Set decision to APPROVED or REJECTED."
        ),
    )

    db_service.update_agent_status("QATradeAgent", "active", tasks_delta=1)
    db_service.insert("qa_decisions", {
        "cycle_id": cycle_id,
        "decision": qa_output.decision,
        "direction": qa_output.direction,
        "entry_price": qa_output.entry_price,
        "stop_loss": qa_output.stop_loss,
        "take_profit_1": qa_output.take_profit_1,
        "take_profit_2": qa_output.take_profit_2,
        "lot_size": qa_output.lot_size,
        "risk_reward_ratio": qa_output.risk_reward_ratio,
        "combined_confidence": qa_output.combined_confidence,
        "rejection_reason": qa_output.rejection_reason,
        "summary": qa_output.summary,
    })

    logger.info(f"=== QA TRADE AGENT COMPLETE: {qa_output.decision} ===")
    return qa_output


# ─────────────────────────────────────────────
# TELEGRAM REPORT AGENT
# ─────────────────────────────────────────────

def run_telegram_report_agent(cycle_id: str, qa_decision: QATradeDecision) -> Optional[str]:
    """
    If QA approved: sends Telegram trade signal with inline keyboard.
    Stores pending signal awaiting human approval.
    Returns signal_id if approved, None if rejected.
    """
    if qa_decision.decision != "APPROVED":
        send_telegram_notification.func(
            title="XAU/USD Trade Signal Rejected",
            message=(
                f"QA Agent rejected trade signal for cycle {cycle_id[:8]}.\n"
                f"Reason: {qa_decision.rejection_reason or 'Insufficient confluence or RR not met.'}\n\n"
                f"Direction tested: {qa_decision.direction}\n"
                f"Fundamental: {qa_decision.fundamental_confidence:.0%} | "
                f"Technical: {qa_decision.technical_confidence:.0%}"
            ),
            level="info",
        )
        logger.info("TelegramReportAgent: Signal rejected — notification sent.")
        return None

    signal_id = str(uuid.uuid4())
    signal_data = {
        "signal_id": signal_id,
        "cycle_id": cycle_id,
        "direction": qa_decision.direction,
        "entry_price": qa_decision.entry_price,
        "stop_loss": qa_decision.stop_loss,
        "take_profit_1": qa_decision.take_profit_1,
        "take_profit_2": qa_decision.take_profit_2,
        "lot_size": qa_decision.lot_size,
        "risk_reward_ratio": qa_decision.risk_reward_ratio,
        "account_risk_pct": qa_decision.account_risk_pct,
        "fundamental_confidence": qa_decision.fundamental_confidence,
        "technical_confidence": qa_decision.technical_confidence,
        "combined_confidence": qa_decision.combined_confidence,
        "fundamental_reason": qa_decision.fundamental_reason,
        "technical_reason": qa_decision.technical_reason,
        "status": "pending_approval",
    }
    db_service.insert("pending_signals", signal_data)
    db_service.update_agent_status("TelegramReportAgent", "active", tasks_delta=1)

    result = send_telegram_trade_signal.func(json.dumps(signal_data))
    msg_id_match = re.search(r"message_id=(\d+)", result)
    if msg_id_match:
        msg_id = int(msg_id_match.group(1))
        db_service.update("pending_signals", {"signal_id": signal_id}, {"telegram_message_id": msg_id})

    logger.info(f"TelegramReportAgent: Signal {signal_id[:8]} sent. Awaiting human approval.")
    return signal_id


# ─────────────────────────────────────────────
# TELEGRAM APPROVAL CALLBACK (called from webhook)
# ─────────────────────────────────────────────

def process_telegram_approval(signal_id: str, action: str) -> Dict[str, Any]:
    """
    Processes a Telegram Inline Keyboard callback (approve/reject).
    Called by the FastAPI Telegram webhook route.
    """
    signals = db_service.select("pending_signals", {"signal_id": signal_id})
    if not signals:
        logger.error(f"process_telegram_approval: Signal {signal_id[:8]} not found.")
        return {"status": "error", "message": "Signal not found."}

    signal = signals[0]
    if signal.get("status") != "pending_approval":
        return {"status": "error", "message": f"Signal already processed: {signal.get('status')}"}

    if action == "approve":
        # Execute paper trade (immutable after this)
        trade_id = str(uuid.uuid4())
        direction = signal.get("direction", "BUY")
        entry = signal.get("entry_price", 0.0)
        sl = signal.get("stop_loss", 0.0)
        tp1 = signal.get("take_profit_1", 0.0)
        lot = signal.get("lot_size", 0.01)
        rr = signal.get("risk_reward_ratio", 0.0)
        confidence = signal.get("combined_confidence", 0.0)
        reasoning = (
            f"Fundamental: {signal.get('fundamental_reason', '')[:200]}\n"
            f"Technical: {signal.get('technical_reason', '')[:200]}"
        )

        # Lock the trade journal entry
        db_service.insert("trade_journal", {
            "trade_id": trade_id,
            "signal_id": signal_id,
            "cycle_id": signal.get("cycle_id", ""),
            "direction": direction,
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit_1": tp1,
            "take_profit_2": signal.get("take_profit_2"),
            "lot_size": lot,
            "risk_reward_ratio": rr,
            "account_risk_pct": signal.get("account_risk_pct", 1.0),
            "fundamental_reason": signal.get("fundamental_reason", ""),
            "technical_reason": signal.get("technical_reason", ""),
            "combined_confidence": confidence,
            "status": "active",
            "locked": True,
        })

        # Also execute paper trade for performance tracking
        execute_paper_trade.func(
            direction=direction,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp1,
            confidence_score=confidence,
            reasoning=reasoning,
            cycle_id=signal.get("cycle_id", ""),
        )

        db_service.update("pending_signals", {"signal_id": signal_id}, {"status": "executed"})
        db_service.update_agent_status("TradeExecutionAgent", "active", tasks_delta=1)
        db_service.update_agent_status("TradeJournalAgent", "active", tasks_delta=1)

        send_telegram_notification.func(
            title=f"Trade EXECUTED — XAU/USD {direction}",
            message=(
                f"Trade ID: {trade_id[:8]}\n"
                f"Direction: {direction}\n"
                f"Entry: ${entry:.2f} | SL: ${sl:.2f} | TP1: ${tp1:.2f}\n"
                f"Lot Size: {lot} | RR: 1:{rr:.1f}\n"
                f"Confidence: {confidence * 100:.0f}%\n\n"
                "Trade journal entry locked. No modifications allowed."
            ),
            level="info",
        )
        logger.info(f"TradeExecutionAgent: Trade {trade_id[:8]} executed and journal locked.")
        return {"status": "executed", "trade_id": trade_id}

    else:  # reject
        db_service.update("pending_signals", {"signal_id": signal_id}, {"status": "rejected"})
        send_telegram_notification.func(
            title="Trade REJECTED by User",
            message=f"Signal {signal_id[:8]} rejected manually via Telegram. No trade executed.",
            level="info",
        )
        logger.info(f"TelegramReportAgent: Signal {signal_id[:8]} rejected by user.")
        return {"status": "rejected", "signal_id": signal_id}


# ─────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────

def create_xauusd_pipeline(cycle_id: str) -> Dict[str, Any]:
    """
    Main orchestration pipeline.
    Runs Fundamental + Technical tracks in PARALLEL, then QA, then Telegram.
    """
    llm = get_llm()
    results = {}

    logger.info(f"Pipeline [{cycle_id[:8]}]: Starting parallel research tracks...")
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="xauusd_research") as executor:
        fundamental_future = executor.submit(run_fundamental_research, llm, cycle_id)
        technical_future = executor.submit(run_technical_research, llm, cycle_id)

        for future in as_completed([fundamental_future, technical_future]):
            try:
                outcome = future.result()
                if isinstance(outcome, FundamentalDirectionOutput):
                    results["fundamental"] = outcome
                    logger.info(f"Pipeline: Fundamental track done — {outcome.direction}")
                elif isinstance(outcome, TechnicalDirectionOutput):
                    results["technical"] = outcome
                    logger.info(f"Pipeline: Technical track done — {outcome.direction}")
            except Exception as e:
                logger.error(f"Pipeline research track failed: {e}")
                raise

    if "fundamental" not in results or "technical" not in results:
        raise RuntimeError("Pipeline: One or both research tracks failed.")

    qa_decision = run_qa_trade_agent(
        llm=llm,
        cycle_id=cycle_id,
        fundamental=results["fundamental"],
        technical=results["technical"],
    )
    results["qa"] = qa_decision

    signal_id = run_telegram_report_agent(cycle_id, qa_decision)
    results["signal_id"] = signal_id

    return {
        "fundamental": {
            "direction": results["fundamental"].direction,
            "confidence": results["fundamental"].confidence,
            "key_drivers": results["fundamental"].key_drivers,
            "summary": results["fundamental"].summary,
        },
        "technical": {
            "direction": results["technical"].direction,
            "confidence": results["technical"].confidence,
            "htf_bias": results["technical"].htf_bias,
            "ltf_entry_signal": results["technical"].ltf_entry_signal,
            "entry_zone": results["technical"].entry_zone,
            "summary": results["technical"].summary,
        },
        "qa": results["qa"].dict(),
        "signal_id": signal_id,
        "cycle_id": cycle_id,
    }


# Backward compatibility alias
def create_market_crew_flow(cycle_id: str) -> Dict[str, Any]:
    """Alias for create_xauusd_pipeline for backward compatibility."""
    return create_xauusd_pipeline(cycle_id)
