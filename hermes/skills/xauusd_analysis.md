"""
XAUUSD Analysis Hermes Skill
============================
A reusable Hermes Agent skill that defines the complete XAUUSD
market analysis workflow. This skill can be invoked on-demand
by Hermes Agent, and defines the step-by-step analytical pipeline
followed by all crew agents.

Usage via Hermes CLI:
  @hermes use xauusd_analysis

Usage via Telegram:
  /cycle
"""

# XAUUSD Market Analysis Skill — Hermes Agent Framework
# Author: XAUUSD Agentic Company
# Version: 2.0 (Hermes-Enhanced)

## Purpose
This skill orchestrates a complete XAUUSD (Gold spot price) market analysis cycle
using a 6-agent crew. Each agent has a specific role in the analysis pipeline.

## When to Use
- When asked to analyze gold market conditions
- When triggered by /cycle command in Telegram
- When the APScheduler or Hermes cron fires a scheduled analysis
- When manually triggered from the dashboard System Execution toggle

## Agent Pipeline

### Step 1: Correlation Analysis (CorrelationAgent)
Fetch and analyze correlated instrument prices:
- **Tools**: fetch_forex_prices, fetch_commodities_prices, fetch_crypto_prices, fetch_market_indices, fetch_treasury_yields, fetch_news_rss, scrape_kitco_news
- **Goal**: Determine if macro correlations are net bullish or bearish for Gold
- **Output**: Structured CorrelationReport with pair_correlations[], news_impacts[], overall_confluence_score (0-100), summary

Key correlation rules:
- DXY rising above 104.5 → BEARISH for Gold (inverse correlation -0.85)
- US10Y yields > 4.5% → BEARISH for Gold (opportunity cost pressure)
- EURUSD rising → BULLISH for Gold (USD weakness proxy)
- Silver (XAG) rising → BULLISH for Gold (metals basket confirmation)
- VIX above 20 → BULLISH for Gold (risk-off demand)
- S&P 500 falling significantly → BULLISH for Gold (safe haven flows)

### Step 2: News & Sentiment Analysis (NewsAgent)
Fetch and analyze gold-specific news and economic calendar:
- **Tools**: fetch_gold_price, fetch_news_rss, analyze_news_sentiment, fetch_economic_calendar, scrape_forex_factory_calendar, scrape_kitco_news
- **Goal**: Determine overall news sentiment and identify high-impact events
- **Output**: Structured GoldNewsReport with news_items[], market_sentiment, is_high_impact, summary

High-impact event rules (only these qualify as HIGH IMPACT):
- FOMC Rate Decision / Powell Speech
- CPI (Consumer Price Index)
- NFP (Non-Farm Payrolls)
- GDP releases
- Emergency Fed meetings

### Step 3: Trade Signal Generation (TradingAgent)
Synthesize research into a paper trade decision:
- **Tools**: fetch_gold_price, execute_paper_trade
- **Input**: CorrelationReport.summary + GoldNewsReport.summary
- **Goal**: Generate BUY, SELL, or HOLD decision with precise levels
- **Output**: Structured TradeSignal

Trade rules (MANDATORY):
- Risk/Reward minimum: 1:1.5 (e.g., 15 pip risk → minimum 22.5 pip reward)
- Max position size: 0.5 lots
- SL must be below entry for BUY; above entry for SELL
- TP must be above entry for BUY; below entry for SELL
- If confluence is mixed or < 50%, select HOLD
- Confidence score must reflect actual conviction (not inflated)

### Step 4: Quality Assurance (QAAgent)
Audit the trade signal for logical errors and improvements:
- **Tools**: fetch_gold_price
- **Goal**: Validate trade signal against research findings and trade rules
- **Output**: Structured QAReport with approval_status: 'approved' | 'approved_with_adjustments' | 'rejected'

QA checklist:
- SL/TP direction matches trade direction
- Risk/Reward ratio meets minimum 1:1.5
- Signal direction aligns with correlation and news sentiment
- Confidence score is proportionate to evidence quality
- If rejected: mark trade signal as expired in DB

### Step 5: Performance Analysis (PerformanceAgent)
Calculate portfolio performance metrics from all closed trades:
- **Tools**: fetch_trade_performance
- **Goal**: Compile Win Rate, Net PnL, Sharpe Ratio, Max Drawdown, Profit Factor
- **Output**: Structured PerformanceReport with agent_scores dict

### Step 6: Supervision & Telegram Report (SupervisorAgent)
Monitor system health, apply teacher feedback, and send daily report:
- **Tools**: check_agent_health, restart_agent_node, record_teacher_feedback, fetch_trade_performance, send_telegram_notification
- **Goal**: Ensure all agents are healthy, apply lessons from underperforming trades, publish Telegram report
- **Output**: Structured SupervisorReport with actions_taken[], daily_summary, telegram_sent

## Hermes Memory Integration
After every cycle, the following is automatically saved to Hermes Memory:
- Any QA-rejected signals → saved as TradingAgent lesson
- SL hits on closed trades → saved as TradingAgent lesson
- Successful high-confidence trades → saved as TradingAgent positive reinforcement
- Agent health issues → saved as SupervisorAgent system lessons

## Error Handling
- If any agent fails, the cycle is marked as 'failed' in analysis_cycles table
- An audit log entry is created for the failure
- Supervisor Agent is notified via Telegram
- The next cycle will retry all agents fresh

## Output Format
The cycle returns a dict with keys:
  - correlation: CorrelationReport dict
  - news: GoldNewsReport dict
  - trade: TradeSignal dict
  - qa: QAReport dict
  - performance: PerformanceReport dict
  - supervisor: SupervisorReport dict
