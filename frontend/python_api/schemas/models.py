from pydantic import BaseModel, Field
from typing import List, Dict


# Correlation Report model (Agent 1 Output)
class PairCorrelation(BaseModel):
    pair: str = Field(
        ...,
        description="The forex currency pair or instrument (e.g., DXY, EURUSD, US10Y, BTC)",
    )
    correlation_score: float = Field(
        ..., description="Correlation score with XAUUSD from -1.0 to 1.0"
    )
    trend: str = Field(
        ..., description="Current trend: bullish, bearish, or rangebound"
    )
    impact_on_gold: str = Field(
        ...,
        description="Description of how this instrument's current status is impacting Gold price",
    )


class NewsImpactItem(BaseModel):
    headline: str = Field(..., description="Headline of the news article")
    source: str = Field(..., description="Publisher name")
    sentiment: str = Field(..., description="bullish, bearish, or neutral")
    impact_score: float = Field(
        ...,
        description="Estimated impact magnitude on Gold from 0.0 (none) to 10.0 (extreme)",
    )


class CorrelationReport(BaseModel):
    pair_correlations: List[PairCorrelation] = Field(
        ..., description="Analysis of correlated pairs"
    )
    news_impacts: List[NewsImpactItem] = Field(
        ..., description="News events of correlated pairs and their impacts"
    )
    overall_confluence_score: float = Field(
        ..., description="Combined alignment score from 0.0 to 100.0"
    )
    summary: str = Field(
        ..., description="Detailed text summary of the correlation findings"
    )


# Gold News Report model (Agent 2 Output)
class NewsItem(BaseModel):
    title: str = Field(..., description="Title of the news article")
    source: str = Field(..., description="Publisher name")
    url: str = Field(..., description="URL link to article")
    sentiment: str = Field(..., description="bullish, bearish, or neutral")
    impact_level: str = Field(..., description="low, medium, or high impact level")


class PairImpact(BaseModel):
    pair: str = Field(..., description="The forex pair impacted")
    expected_impact: str = Field(
        ..., description="Description of the expected movement"
    )


class GoldNewsReport(BaseModel):
    news_items: List[NewsItem] = Field(
        ..., description="List of gold-related news articles"
    )
    market_sentiment: str = Field(
        ..., description="Overall market sentiment: bullish, bearish, or neutral"
    )
    impact_on_pairs: List[PairImpact] = Field(
        ..., description="How XAUUSD movements are expected to impact correlated pairs"
    )
    is_high_impact: bool = Field(
        ...,
        description="True if a major event like CPI, NFP, or rate decision is released",
    )
    summary: str = Field(
        ..., description="Detailed textual summary of gold news and market dynamics"
    )


# Trade Signal model (Agent 3 Output)
class TradeSignal(BaseModel):
    direction: str = Field(..., description="BUY, SELL, or HOLD")
    entry_price: float = Field(..., description="Suggested entry spot price")
    stop_loss: float = Field(..., description="Calculated stop loss price")
    take_profit: float = Field(..., description="Calculated take profit price")
    confidence_score: float = Field(
        ..., description="Overall signal confidence from 0.0 to 1.0"
    )
    reasoning: str = Field(
        ...,
        description="Detailed trading rationale explaining why this trade was chosen",
    )


# QA Report model (Agent 4 Output)
class QAValidationIssue(BaseModel):
    agent: str = Field(
        ..., description="The name of the agent responsible for the issue"
    )
    issue: str = Field(
        ..., description="Description of the flaw or inconsistency found"
    )
    severity: str = Field(..., description="low, medium, or high severity")


class QAImprovementSuggestion(BaseModel):
    agent: str = Field(..., description="The agent that needs improvement")
    suggestion: str = Field(
        ..., description="Specific suggestion to improve accuracy/correct mistakes"
    )


class QAReport(BaseModel):
    issues_found: List[QAValidationIssue] = Field(
        ..., description="List of issues and logical errors detected"
    )
    improvements: List[QAImprovementSuggestion] = Field(
        ..., description="Actionable improvement feedback loops for workers"
    )
    approval_status: str = Field(
        ..., description="approved, rejected, or needs_improvement"
    )
    confidence_adjustment: float = Field(
        ...,
        description="Adjustment to trade signal confidence score (e.g. -0.1 or +0.0)",
    )
    summary: str = Field(..., description="Text summary of the QA review findings")


# Performance Report model (Agent 5 Output)
class PerformanceReport(BaseModel):
    win_rate: float = Field(
        ..., description="Percentage of winning trades out of total closed trades"
    )
    total_pnl: float = Field(
        ..., description="Net profits or losses in USD on paper trading account"
    )
    sharpe_ratio: float = Field(..., description="Estimated risk-adjusted return ratio")
    max_drawdown: float = Field(..., description="Maximum percentage equity decline")
    profit_factor: float = Field(
        ..., description="Gross profits divided by gross losses"
    )
    total_trades: int = Field(..., description="Number of trades total")
    winning_trades: int = Field(..., description="Number of wins")
    losing_trades: int = Field(..., description="Number of losses")
    agent_scores: Dict[str, float] = Field(
        ..., description="Estimated accuracy ratings for each worker agent (0.0 to 1.0)"
    )


# Supervisor Report model (Agent 6 Output)
class AgentStatusReport(BaseModel):
    agent: str = Field(..., description="Name of the agent")
    status: str = Field(..., description="active, paused, error, or restarting")
    health_score: float = Field(
        ..., description="Estimated health rating from 0.0 to 1.0"
    )


class SupervisorActionItem(BaseModel):
    action: str = Field(
        ...,
        description="The corrective action taken (e.g., RESTART, RECONFIGURE, LOG_LESSON)",
    )
    target_agent: str = Field(..., description="The agent that was corrected")
    reason: str = Field(
        ..., description="Description of the mistake or failure detected"
    )
    result: str = Field(..., description="Outcome of the correction")


class SupervisorReport(BaseModel):
    agent_statuses: List[AgentStatusReport] = Field(
        ..., description="Health status of all agents"
    )
    actions_taken: List[SupervisorActionItem] = Field(
        ..., description="Corrective actions initiated by Supervisor"
    )
    daily_summary: str = Field(
        ..., description="Daily status report text to be transmitted to Telegram"
    )
    telegram_sent: bool = Field(
        ..., description="Whether a message was queued for sending to Telegram"
    )
