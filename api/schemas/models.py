from pydantic import BaseModel, Field
from typing import List, Dict, Optional


# ─────────────────────────────────────────────
# FUNDAMENTAL RESEARCH TEAM
# ─────────────────────────────────────────────


class NewsItem(BaseModel):
    title: str = Field(..., description="Headline of the news article")
    source: str = Field(..., description="Publisher name")
    url: str = Field(..., description="URL link to article")
    sentiment: str = Field(..., description="bullish, bearish, or neutral")
    impact_level: str = Field(..., description="low, medium, or high impact level")


class EconomicEvent(BaseModel):
    event: str = Field(..., description="Event name e.g. CPI, NFP, FOMC")
    time_utc: str = Field(..., description="Scheduled time in UTC")
    impact: str = Field(..., description="high, medium, or low")
    expected_effect: str = Field(
        ..., description="Expected bullish/bearish effect on gold"
    )


class NewsResearchOutput(BaseModel):
    news_items: List[NewsItem] = Field(
        ..., description="Latest gold-related news articles"
    )
    economic_events: List[EconomicEvent] = Field(
        ..., description="High-impact scheduled events today"
    )
    fed_stance: str = Field(
        ...,
        description="hawkish, dovish, or neutral based on recent Fed communications",
    )
    inflation_data: str = Field(
        ..., description="Latest CPI / inflation reading summary"
    )
    is_high_impact_day: bool = Field(
        ..., description="True if a major event (CPI, NFP, FOMC) is today"
    )
    sentiment_score: float = Field(
        ..., description="Net sentiment score from -1.0 (bearish) to +1.0 (bullish)"
    )
    summary: str = Field(..., description="Detailed narrative summary of news findings")


class CorrelationPair(BaseModel):
    instrument: str = Field(
        ..., description="Instrument name e.g. DXY, US10Y, BTC, VIX"
    )
    current_value: str = Field(..., description="Current price or level")
    trend: str = Field(..., description="bullish, bearish, or ranging")
    correlation_to_gold: str = Field(..., description="inverse or positive")
    impact_score: float = Field(..., description="Impact score -10.0 to +10.0 on gold")
    analysis: str = Field(..., description="1-2 sentence explanation of impact")


class CorrelationOutput(BaseModel):
    correlations: List[CorrelationPair] = Field(
        ..., description="Correlated instrument analysis"
    )
    dxy_bias: str = Field(..., description="DXY trend bias: strengthening or weakening")
    yields_bias: str = Field(..., description="US10Y yields bias: rising or falling")
    risk_sentiment: str = Field(..., description="risk-on or risk-off environment")
    confluence_score: float = Field(
        ..., description="Overall confluence score 0.0 to 100.0"
    )
    summary: str = Field(..., description="Detailed narrative summary of correlations")


class FundamentalDirectionOutput(BaseModel):
    direction: str = Field(..., description="BULLISH, BEARISH, or NEUTRAL")
    confidence: float = Field(..., description="Confidence score 0.0 to 1.0")
    key_drivers: List[str] = Field(
        ..., description="Top 3-5 fundamental reasons for direction"
    )
    risk_factors: List[str] = Field(
        ..., description="Events or data that could invalidate the direction"
    )
    summary: str = Field(..., description="Full fundamental analysis narrative")


# ─────────────────────────────────────────────
# TECHNICAL RESEARCH TEAM
# ─────────────────────────────────────────────


class TimeframeAnalysis(BaseModel):
    timeframe: str = Field(..., description="Timeframe e.g. 1W, 1D, 4H, 1H, 15M, 5M")
    trend: str = Field(..., description="BULLISH, BEARISH, or RANGING")
    structure: str = Field(
        ...,
        description="Market structure: HH/HL (uptrend), LH/LL (downtrend), or ranging",
    )
    key_support: float = Field(..., description="Nearest major support level")
    key_resistance: float = Field(..., description="Nearest major resistance level")
    order_block: Optional[str] = Field(None, description="Identified order block zone")
    liquidity_zone: Optional[str] = Field(
        None, description="Identified liquidity pool zone"
    )
    candle_pattern: Optional[str] = Field(
        None, description="Notable candle pattern if any"
    )
    analysis: str = Field(
        ..., description="Brief narrative of technical conditions on this timeframe"
    )


class TechnicalDirectionOutput(BaseModel):
    direction: str = Field(..., description="BULLISH, BEARISH, or NEUTRAL")
    confidence: float = Field(..., description="Confidence score 0.0 to 1.0")
    timeframe_analyses: List[TimeframeAnalysis] = Field(
        ..., description="Individual analysis per timeframe"
    )
    htf_bias: str = Field(
        ...,
        description="Higher timeframe bias (1W+1D combined): BULLISH, BEARISH, or NEUTRAL",
    )
    ltf_entry_signal: str = Field(
        ..., description="Lower timeframe entry signal: BUY, SELL, or WAIT"
    )
    entry_zone: str = Field(..., description="Ideal entry zone e.g. '$2635 - $2640'")
    invalidation_level: float = Field(
        ..., description="Price that invalidates the technical setup"
    )
    summary: str = Field(..., description="Full multi-timeframe technical narrative")


# ─────────────────────────────────────────────
# QA TRADE AGENT
# ─────────────────────────────────────────────


class QAIssue(BaseModel):
    issue_type: str = Field(
        ..., description="confluence, rr_ratio, entry_quality, or risk"
    )
    description: str = Field(..., description="Description of the issue found")
    severity: str = Field(..., description="low, medium, or high")


class QATradeDecision(BaseModel):
    decision: str = Field(..., description="APPROVED or REJECTED")
    direction: str = Field(..., description="BUY, SELL, or HOLD")
    entry_price: float = Field(..., description="Recommended entry spot price")
    stop_loss: float = Field(..., description="Stop loss price level")
    take_profit_1: float = Field(
        ..., description="First take profit target (minimum RR 1:3)"
    )
    take_profit_2: Optional[float] = Field(
        None, description="Optional second take profit target"
    )
    lot_size: float = Field(
        ..., description="Calculated lot size based on 1% account risk"
    )
    risk_reward_ratio: float = Field(
        ..., description="Actual RR ratio e.g. 3.5 means 1:3.5"
    )
    account_risk_pct: float = Field(
        ..., description="Percentage of account at risk e.g. 1.0"
    )
    fundamental_confidence: float = Field(
        ..., description="Fundamental direction confidence 0.0-1.0"
    )
    technical_confidence: float = Field(
        ..., description="Technical direction confidence 0.0-1.0"
    )
    combined_confidence: float = Field(
        ..., description="Combined weighted confidence score 0.0-1.0"
    )
    issues_found: List[QAIssue] = Field(
        default_factory=list, description="List of issues detected"
    )
    rejection_reason: Optional[str] = Field(
        None, description="Reason for rejection if REJECTED"
    )
    fundamental_reason: str = Field(..., description="Summary of fundamental reasoning")
    technical_reason: str = Field(..., description="Summary of technical reasoning")
    summary: str = Field(..., description="Full QA validation narrative")


class PendingTradeSignal(BaseModel):
    signal_id: str = Field(..., description="Unique signal UUID")
    cycle_id: str = Field(..., description="Parent cycle UUID")
    direction: str = Field(..., description="BUY or SELL")
    entry_price: float = Field(default=0.0)
    stop_loss: float = Field(default=0.0)
    take_profit_1: float = Field(default=0.0)
    take_profit_2: Optional[float] = None
    lot_size: float = Field(default=0.01)
    risk_reward_ratio: float = Field(default=0.0)
    account_risk_pct: float = Field(default=1.0)
    fundamental_confidence: float = Field(default=0.0)
    technical_confidence: float = Field(default=0.0)
    combined_confidence: float = Field(default=0.0)
    fundamental_reason: str = Field(default="")
    technical_reason: str = Field(default="")
    status: str = Field(default="pending_approval")
    telegram_message_id: Optional[int] = None


class TradeJournalEntry(BaseModel):
    trade_id: str = Field(..., description="Unique trade UUID")
    signal_id: str = Field(..., description="Parent signal UUID")
    cycle_id: str = Field(..., description="Parent cycle UUID")
    direction: str = Field(..., description="BUY or SELL")
    entry_price: float = Field(default=0.0)
    stop_loss: float = Field(default=0.0)
    take_profit_1: float = Field(default=0.0)
    take_profit_2: Optional[float] = None
    lot_size: float = Field(default=0.01)
    risk_reward_ratio: float = Field(default=0.0)
    account_risk_pct: float = Field(default=1.0)
    fundamental_reason: str = Field(default="")
    technical_reason: str = Field(default="")
    combined_confidence: float = Field(default=0.0)
    status: str = Field(default="active")
    close_price: Optional[float] = None
    pnl_pips: float = Field(default=0.0)
    pnl_usd: float = Field(default=0.0)
    locked: bool = Field(default=True)


# ─────────────────────────────────────────────
# PERFORMANCE & LEARNING TEAM
# ─────────────────────────────────────────────


class TradeAttribution(BaseModel):
    trade_id: str = Field(..., description="Trade ID")
    outcome: str = Field(..., description="win or loss")
    fundamental_factor: str = Field(
        ..., description="How fundamental analysis contributed"
    )
    technical_factor: str = Field(..., description="How technical analysis contributed")
    entry_quality: str = Field(..., description="Assessment of entry timing quality")
    timeframe_alignment: str = Field(..., description="How well timeframes aligned")
    rr_achieved: float = Field(..., description="Actual RR achieved vs planned")


class LearningRecommendation(BaseModel):
    recommendation_id: str = Field(..., description="Unique recommendation UUID")
    category: str = Field(
        ...,
        description="entry_criteria, rr_requirements, timeframe_weights, confidence_thresholds",
    )
    proposed_change: str = Field(
        ..., description="Specific proposed change with rationale"
    )
    supporting_evidence: str = Field(
        ..., description="Trade data supporting this recommendation"
    )
    expected_improvement: str = Field(
        ..., description="Expected improvement in win rate or RR"
    )
    adopted: bool = Field(default=False)
    adopted_at: Optional[str] = None


class PerformanceSummary(BaseModel):
    total_trades: int = Field(default=0)
    winning_trades: int = Field(default=0)
    losing_trades: int = Field(default=0)
    win_rate: float = Field(default=0.0)
    total_pnl_usd: float = Field(default=0.0)
    avg_rr_achieved: float = Field(default=0.0)
    max_drawdown_pct: float = Field(default=0.0)
    profit_factor: float = Field(default=1.0)
    sharpe_ratio: float = Field(default=0.0)
    best_setup_pattern: str = Field(default="")
    worst_setup_pattern: str = Field(default="")
    attributions: List[TradeAttribution] = Field(default_factory=list)
    weekly_report: str = Field(default="")
    monthly_report: str = Field(default="")


class AgentHealthStatus(BaseModel):
    agent: str = Field(..., description="Agent name")
    status: str = Field(..., description="active, error, or idle")
    health_score: float = Field(default=1.0)
    tasks_completed: int = Field(default=0)
    errors: int = Field(default=0)


class SupervisorReport(BaseModel):
    agent_statuses: List[AgentHealthStatus] = Field(default_factory=list)
    actions_taken: List[str] = Field(default_factory=list)
    cycle_summary: str = Field(default="")
    telegram_sent: bool = Field(default=False)


# ─────────────────────────────────────────────
# LEGACY COMPATIBILITY (kept for existing dashboard routes)
# ─────────────────────────────────────────────


class QAReport(BaseModel):
    issues_found: List[QAIssue] = Field(default_factory=list)
    approval_status: str = Field(default="approved")
    confidence_adjustment: float = Field(default=0.0)
    summary: str = Field(default="")


class PerformanceReport(BaseModel):
    win_rate: float = Field(default=0.0)
    total_pnl: float = Field(default=0.0)
    sharpe_ratio: float = Field(default=0.0)
    max_drawdown: float = Field(default=0.0)
    profit_factor: float = Field(default=1.0)
    total_trades: int = Field(default=0)
    winning_trades: int = Field(default=0)
    losing_trades: int = Field(default=0)
    agent_scores: Dict[str, float] = Field(default_factory=dict)


class TradeSignal(BaseModel):
    direction: str = Field(default="HOLD")
    entry_price: float = Field(default=0.0)
    stop_loss: float = Field(default=0.0)
    take_profit: float = Field(default=0.0)
    confidence_score: float = Field(default=0.0)
    reasoning: str = Field(default="")
