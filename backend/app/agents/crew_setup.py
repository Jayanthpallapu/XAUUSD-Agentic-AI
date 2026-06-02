import logging
from typing import Dict, Any, List
from crewai import Agent, Task, Crew, Process, LLM
from app.config import settings
from app.services.supabase_client import db_service
from app.models.models import (
    CorrelationReport,
    GoldNewsReport,
    TradeSignal,
    QAReport,
    PerformanceReport,
    SupervisorReport
)

# Import all tools
from app.tools.market_data import (
    fetch_gold_price,
    fetch_forex_prices,
    fetch_commodities_prices,
    fetch_crypto_prices,
    fetch_market_indices,
    fetch_treasury_yields
)
from app.tools.news_calendar import (
    fetch_news_rss,
    analyze_news_sentiment,
    fetch_economic_calendar
)
from app.tools.trading_performance import (
    execute_paper_trade,
    fetch_trade_performance,
    record_teacher_feedback
)
from app.tools.system import (
    check_agent_health,
    restart_agent_node,
    send_telegram_notification
)

logger = logging.getLogger("crew_setup")

# Initialize Groq LLM
def get_llm(model_name: str = "groq/llama-3.3-70b-versatile") -> LLM:
    if settings.GROQ_API_KEY:
        try:
            return LLM(
                model=model_name,
                api_key=settings.GROQ_API_KEY,
                temperature=0.2
            )
        except Exception as e:
            logger.error(f"Error creating LLM: {e}. Falling back to default system model.")
    
    # Return a basic LLM structure (CrewAI might fail if api_key is blank, so we inject dummy text)
    return LLM(
        model="groq/llama-3.1-8b-instant",
        api_key="gsk_mock_key_for_offline_runs"
    )

def fetch_lessons_backstory(agent_name: str) -> str:
    """Fetches lessons learned for an agent from the database and formats them for the backstory."""
    try:
        res = db_service.select("agent_registry", {"name": agent_name})
        if res:
            agent = res[0]
            lessons = agent.get("lessons_learned", [])
            if lessons and isinstance(lessons, list):
                formatted = "\nCRITICAL LESSONS LEARNED FROM PAST MISTAKES (You MUST avoid repeating these):\n"
                for idx, item in enumerate(lessons[-5:]):  # Limit to 5 most recent lessons to save tokens
                    formatted += f"Lesson {idx+1}:\n- Past Mistake: {item.get('mistake')}\n- Corrective Action: {item.get('correction')}\n- Teacher Lesson: {item.get('lesson')}\n"
                return formatted
    except Exception as e:
        logger.error(f"Error fetching lessons backstory for {agent_name}: {e}")
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
            fetch_news_rss
        ],
        llm=llm,
        allow_delegation=False,
        max_iter=15,
        verbose=True
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
            fetch_economic_calendar
        ],
        llm=llm,
        allow_delegation=False,
        max_iter=15,
        verbose=True
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
        tools=[
            fetch_gold_price,
            execute_paper_trade
        ],
        llm=llm,
        allow_delegation=False,
        max_iter=15,
        verbose=True
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
        tools=[
            fetch_gold_price
        ],
        llm=llm,
        allow_delegation=False,
        max_iter=15,
        verbose=True
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
        tools=[
            fetch_trade_performance
        ],
        llm=llm,
        allow_delegation=False,
        max_iter=15,
        verbose=True
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
            send_telegram_notification
        ],
        llm=llm,
        allow_delegation=True, # Supervisor can assign actions/tasks
        max_iter=15,
        verbose=True
    )

def create_market_crew_flow(cycle_id: str) -> Dict[str, Any]:
    """Runs the multi-crew agent pipeline and returns the structured outputs of each task."""
    llm = get_llm()
    
    # 1. Instantiate Agents
    corr_agent = create_correlation_agent(llm)
    news_agent = create_news_agent(llm)
    trade_agent = create_trading_agent(llm)
    qa_agent = create_qa_agent(llm)
    perf_agent = create_performance_agent(llm)
    supervisor_agent = create_supervisor_agent(llm)
    
    # 2. Define Tasks
    corr_task = Task(
        description="Fetch forex prices, index prices, crypto rates, commodity rates, and treasury yields. Research how correlated markets are moving. Analyze recent correlated news RSS.",
        expected_output="A structured report evaluating correlation alignment metrics.",
        agent=corr_agent,
        output_pydantic=CorrelationReport
    )
    
    news_task = Task(
        description="Fetch gold spot price, search news RSS for gold market sentiment and economic calendar events. Summarize sentiment and note if any high-impact event (CPI, NFP, GDP, Interest rates) is released today.",
        expected_output="A structured gold news and economic event impact analysis.",
        agent=news_agent,
        output_pydantic=GoldNewsReport
    )
    
    # Run Research Crew in Parallel
    research_crew = Crew(
        agents=[corr_agent, news_agent],
        tasks=[corr_task, news_task],
        process=Process.sequential,  # Run sequentially within the crew, but we call kickoff
        verbose=True
    )
    
    logger.info("Starting Research Crew kickoff...")
    research_results = research_crew.kickoff()
    
    # Extract research outputs
    corr_output = research_results.tasks_output[0].pydantic
    news_output = research_results.tasks_output[1].pydantic
    
    # Save research outputs to database
    db_service.insert("correlation_reports", {
        "cycle_id": cycle_id,
        "pair_correlations": [p.dict() for p in corr_output.pair_correlations],
        "news_impacts": [n.dict() for n in corr_output.news_impacts],
        "overall_confluence_score": corr_output.overall_confluence_score,
        "summary": corr_output.summary
    })
    db_service.update_agent_status("CorrelationAgent", "active", tasks_delta=1)

    db_service.insert("gold_news_reports", {
        "cycle_id": cycle_id,
        "news_items": [n.dict() for n in news_output.news_items],
        "market_sentiment": news_output.market_sentiment,
        "impact_on_pairs": [p.dict() for p in news_output.impact_on_pairs],
        "is_high_impact": news_output.is_high_impact,
        "summary": news_output.summary
    })
    db_service.update_agent_status("NewsAgent", "active", tasks_delta=1)

    # 3. Trading Signal Task (Sequential - uses research outputs in description)
    trade_task = Task(
        description=(
            f"Observe the current gold price. Using the Correlation Report: {corr_output.summary} "
            f"and the Gold News Report: {news_output.summary}, determine if a BUY or SELL setup exists. "
            f"If conditions are mixed or unclear, select HOLD. If placing a trade, call the Paper Trade Executor tool "
            f"with appropriate SL, TP, entry price, and confidence score. Use cycle_id: {cycle_id}."
        ),
        expected_output="A structured BUY/SELL/HOLD trade signal recommendation.",
        agent=trade_agent,
        output_pydantic=TradeSignal
    )
    
    # 4. QA Task (Reviewer)
    qa_task = Task(
        description=(
            "Review the research findings, news analysis, and the resulting Trade Signal. "
            "Audit the trade levels: make sure SL is below entry for BUY, TP is above entry for BUY, etc. "
            "Adjust the trade signal's confidence score if you find logical mistakes or warning signs. "
            "Write specific actionable improvement suggestions for the agents if they made mistakes."
        ),
        expected_output="A detailed QA audit report approving, rejecting, or adjusting the signal.",
        agent=qa_agent,
        output_pydantic=QAReport
    )
    
    analysis_crew = Crew(
        agents=[trade_agent, qa_agent],
        tasks=[trade_task, qa_task],
        process=Process.sequential,
        verbose=True
    )
    
    logger.info("Starting Analysis Crew kickoff...")
    analysis_results = analysis_crew.kickoff()
    
    trade_output = analysis_results.tasks_output[0].pydantic
    qa_output = analysis_results.tasks_output[1].pydantic
    
    db_service.insert("qa_reports", {
        "cycle_id": cycle_id,
        "issues_found": [i.dict() for i in qa_output.issues_found],
        "improvements": [imp.dict() for imp in qa_output.improvements],
        "approval_status": qa_output.approval_status,
        "confidence_adjustment": qa_output.confidence_adjustment,
        "summary": qa_output.summary
    })
    db_service.update_agent_status("TradingAgent", "active", tasks_delta=1)
    db_service.update_agent_status("QAAgent", "active", tasks_delta=1)

    # If the QA agent rejected the trade signal, we update the trade signal in DB to 'rejected'
    if qa_output.approval_status == "rejected":
        # Find the trade inserted during this cycle and update its status to 'expired' or 'rejected'
        signals = db_service.select("trade_signals", {"cycle_id": cycle_id})
        if signals:
            db_service.update("trade_signals", {"id": signals[0]["id"]}, {"status": "expired"})
            logger.info(f"QA Agent rejected trade signal. Trade ID {signals[0]['id'][:8]} marked as expired/rejected.")

    # 5. Performance Monitoring Task
    perf_task = Task(
        description="Analyze closed trade results using the Trade Performance Fetcher tool. Compile portfolio statistics (win rate, total PnL, drawdowns, Sharpe) and assess current agent performance scores.",
        expected_output="A compiled portfolio performance and accuracy scorecard.",
        agent=perf_agent,
        output_pydantic=PerformanceReport
    )
    
    perf_crew = Crew(
        agents=[perf_agent],
        tasks=[perf_task],
        process=Process.sequential,
        verbose=True
    )
    
    logger.info("Starting Performance Crew kickoff...")
    perf_results = perf_crew.kickoff()
    perf_output = perf_results.tasks_output[0].pydantic
    
    db_service.insert("performance_reports", {
        "cycle_id": cycle_id,
        "win_rate": perf_output.win_rate,
        "total_pnl": perf_output.total_pnl,
        "sharpe_ratio": perf_output.sharpe_ratio,
        "max_drawdown": perf_output.max_drawdown,
        "profit_factor": perf_output.profit_factor,
        "total_trades": perf_output.total_trades,
        "winning_trades": perf_output.winning_trades,
        "losing_trades": perf_output.losing_trades,
        "agent_scores": perf_output.agent_scores
    })
    db_service.update_agent_status("PerformanceAgent", "active", tasks_delta=1)

    # 6. Head Supervisor Task
    # Check agent statuses, run health, apply feedback, send Telegram message.
    supervisor_task = Task(
        description=(
            "Run the Agent Health Monitor tool to diagnose node health. If any node has high error counts, "
            "call the Agent Node Restarter. Write teacher feedback notes for the trading agent if any trades "
            "underperformed or failed QA validation, and use the Teacher Feedback Recorder to submit them. "
            "Draft a comprehensive daily execution summary, and call the Telegram Notifier tool to send it."
        ),
        expected_output="A summary of supervisor actions taken and system health.",
        agent=supervisor_agent,
        output_pydantic=SupervisorReport
    )
    
    supervisor_crew = Crew(
        agents=[supervisor_agent],
        tasks=[supervisor_task],
        process=Process.sequential,
        verbose=True
    )
    
    logger.info("Starting Supervisor Crew kickoff...")
    supervisor_results = supervisor_crew.kickoff()
    supervisor_output = supervisor_results.tasks_output[0].pydantic
    
    db_service.insert("supervisor_reports", {
        "cycle_id": cycle_id,
        "agent_statuses": [a.dict() for a in supervisor_output.agent_statuses],
        "actions_taken": [a.dict() for a in supervisor_output.actions_taken],
        "daily_summary": supervisor_output.daily_summary,
        "telegram_sent": supervisor_output.telegram_sent
    })
    db_service.update_agent_status("SupervisorAgent", "active", tasks_delta=1)

    # Return full execution results
    return {
        "correlation": corr_output.dict(),
        "news": news_output.dict(),
        "trade": trade_output.dict(),
        "qa": qa_output.dict(),
        "performance": perf_output.dict(),
        "supervisor": supervisor_output.dict()
    }
