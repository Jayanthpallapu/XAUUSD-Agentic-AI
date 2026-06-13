-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Agent Registry table
CREATE TABLE IF NOT EXISTS agent_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active', -- active, paused, error, restarting
    config JSONB DEFAULT '{}'::jsonb,
    lessons_learned JSONB DEFAULT '[]'::jsonb, -- Array of {timestamp, mistake, correction, lesson}
    last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    avg_response_time_ms FLOAT DEFAULT 0.0,
    accuracy_score FLOAT DEFAULT 1.0, -- 0.0 to 1.0
    total_tasks_completed INTEGER DEFAULT 0,
    total_errors INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Analysis Cycles table
CREATE TABLE IF NOT EXISTS analysis_cycles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_number SERIAL,
    status TEXT NOT NULL DEFAULT 'running', -- running, completed, failed
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_seconds FLOAT
);

-- Correlation Reports table
CREATE TABLE IF NOT EXISTS correlation_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_id UUID REFERENCES analysis_cycles(id) ON DELETE CASCADE,
    pair_correlations JSONB DEFAULT '[]'::jsonb, -- Array of {pair, correlation, trend, impact}
    news_impacts JSONB DEFAULT '[]'::jsonb,
    overall_confluence_score FLOAT DEFAULT 0.0,
    summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Gold News Reports table
CREATE TABLE IF NOT EXISTS gold_news_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_id UUID REFERENCES analysis_cycles(id) ON DELETE CASCADE,
    news_items JSONB DEFAULT '[]'::jsonb, -- Array of {title, source, url, sentiment, impact_level}
    market_sentiment TEXT DEFAULT 'neutral', -- bullish, bearish, neutral
    impact_on_pairs JSONB DEFAULT '[]'::jsonb,
    is_high_impact BOOLEAN DEFAULT FALSE,
    summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Trade Signals (Paper Trades) table
CREATE TABLE IF NOT EXISTS trade_signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_id UUID REFERENCES analysis_cycles(id) ON DELETE CASCADE,
    direction TEXT NOT NULL, -- BUY, SELL, HOLD
    entry_price FLOAT,
    stop_loss FLOAT,
    take_profit FLOAT,
    confidence_score FLOAT,
    reasoning TEXT,
    status TEXT DEFAULT 'pending', -- pending, active, closed_win, closed_loss, expired
    close_price FLOAT,
    pnl_pips FLOAT DEFAULT 0.0,
    pnl_usd FLOAT DEFAULT 0.0,
    teacher_notes TEXT, -- Notes from Head Supervisor on how to improve this signal next time
    opened_at TIMESTAMP WITH TIME ZONE,
    closed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- QA Reports table
CREATE TABLE IF NOT EXISTS qa_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_id UUID REFERENCES analysis_cycles(id) ON DELETE CASCADE,
    issues_found JSONB DEFAULT '[]'::jsonb,
    improvements JSONB DEFAULT '[]'::jsonb,
    approval_status TEXT NOT NULL DEFAULT 'approved', -- approved, rejected, needs_improvement
    confidence_adjustment FLOAT DEFAULT 0.0,
    summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Performance Reports table
CREATE TABLE IF NOT EXISTS performance_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_id UUID REFERENCES analysis_cycles(id) ON DELETE CASCADE,
    win_rate FLOAT DEFAULT 0.0,
    total_pnl FLOAT DEFAULT 0.0,
    sharpe_ratio FLOAT DEFAULT 0.0,
    max_drawdown FLOAT DEFAULT 0.0,
    profit_factor FLOAT DEFAULT 0.0,
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    agent_scores JSONB DEFAULT '{}'::jsonb, -- accuracy score for each agent
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Supervisor Reports table
CREATE TABLE IF NOT EXISTS supervisor_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_id UUID REFERENCES analysis_cycles(id) ON DELETE CASCADE,
    agent_statuses JSONB DEFAULT '[]'::jsonb,
    actions_taken JSONB DEFAULT '[]'::jsonb, -- actions to correct malfunctioning agents
    daily_summary TEXT,
    telegram_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    level TEXT DEFAULT 'info', -- info, warning, critical
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    source_agent TEXT,
    read BOOLEAN DEFAULT FALSE,
    telegram_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Audit Log table
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_name TEXT,
    action TEXT NOT NULL,
    input_data JSONB,
    output_data JSONB,
    duration_ms FLOAT,
    status TEXT DEFAULT 'success', -- success, error
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Fundamental Reports table
CREATE TABLE IF NOT EXISTS fundamental_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_id UUID REFERENCES analysis_cycles(id) ON DELETE CASCADE,
    news_summary TEXT,
    news_sentiment_score FLOAT DEFAULT 0.0,
    is_high_impact_day BOOLEAN DEFAULT FALSE,
    correlation_confluence_score FLOAT DEFAULT 0.0,
    direction TEXT,
    confidence FLOAT,
    key_drivers JSONB DEFAULT '[]'::jsonb,
    risk_factors JSONB DEFAULT '[]'::jsonb,
    summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Technical Reports table
CREATE TABLE IF NOT EXISTS technical_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_id UUID REFERENCES analysis_cycles(id) ON DELETE CASCADE,
    direction TEXT,
    confidence FLOAT,
    htf_bias TEXT,
    ltf_entry_signal TEXT,
    entry_zone TEXT,
    invalidation_level FLOAT,
    timeframe_count INTEGER,
    summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- QA Decisions table
CREATE TABLE IF NOT EXISTS qa_decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_id UUID REFERENCES analysis_cycles(id) ON DELETE CASCADE,
    decision TEXT,
    direction TEXT,
    entry_price FLOAT,
    stop_loss FLOAT,
    take_profit_1 FLOAT,
    take_profit_2 FLOAT,
    lot_size FLOAT,
    risk_reward_ratio FLOAT,
    combined_confidence FLOAT,
    rejection_reason TEXT,
    summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Pending Signals table
CREATE TABLE IF NOT EXISTS pending_signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    signal_id TEXT,
    cycle_id UUID REFERENCES analysis_cycles(id) ON DELETE CASCADE,
    direction TEXT,
    entry_price FLOAT,
    stop_loss FLOAT,
    take_profit_1 FLOAT,
    take_profit_2 FLOAT,
    lot_size FLOAT,
    risk_reward_ratio FLOAT,
    account_risk_pct FLOAT,
    fundamental_confidence FLOAT,
    technical_confidence FLOAT,
    combined_confidence FLOAT,
    fundamental_reason TEXT,
    technical_reason TEXT,
    status TEXT DEFAULT 'pending_approval',
    telegram_message_id INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Trade Journal table
CREATE TABLE IF NOT EXISTS trade_journal (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trade_id TEXT,
    signal_id TEXT,
    cycle_id TEXT,
    direction TEXT,
    entry_price FLOAT,
    stop_loss FLOAT,
    take_profit_1 FLOAT,
    take_profit_2 FLOAT,
    lot_size FLOAT,
    risk_reward_ratio FLOAT,
    account_risk_pct FLOAT,
    fundamental_reason TEXT,
    technical_reason TEXT,
    combined_confidence FLOAT,
    status TEXT DEFAULT 'active',
    locked BOOLEAN DEFAULT TRUE,
    close_price FLOAT,
    pnl_pips FLOAT DEFAULT 0.0,
    pnl_usd FLOAT DEFAULT 0.0,
    opened_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Learning Recommendations table
CREATE TABLE IF NOT EXISTS learning_recommendations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recommendation_id TEXT,
    category TEXT,
    proposed_change TEXT,
    supporting_evidence TEXT,
    expected_improvement TEXT,
    adopted BOOLEAN DEFAULT FALSE,
    adopted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Seed Agent Registry
INSERT INTO agent_registry (name, role, status) VALUES
('NewsResearchAgent', 'Fundamental — News & Sentiment Researcher', 'active'),
('CorrelationAgent', 'Fundamental — Macro Correlation Analyst', 'active'),
('FundamentalDirectionAgent', 'Fundamental — Direction Synthesizer', 'active'),
('TechnicalDirectionAgent', 'Technical — Multi-Timeframe Synthesizer', 'active'),
('Analyst_1W', 'Technical — 1-Week Timeframe Analyst', 'active'),
('Analyst_1D', 'Technical — 1-Day Timeframe Analyst', 'active'),
('Analyst_4H', 'Technical — 4-Hour Timeframe Analyst', 'active'),
('Analyst_1H', 'Technical — 1-Hour Timeframe Analyst', 'active'),
('Analyst_15M', 'Technical — 15-Minute Timeframe Analyst', 'active'),
('Analyst_5M', 'Technical — 5-Minute Timeframe Analyst', 'active'),
('QATradeAgent', 'QA — Risk Manager & Trade Validator', 'active'),
('TelegramReportAgent', 'QA — Telegram Signal Publisher', 'active'),
('TradeExecutionAgent', 'Execution — Paper Trade Executor', 'active'),
('TradeJournalAgent', 'Execution — Immutable Trade Journal', 'active'),
('PerformanceAgent', 'Performance — Analytics & Attribution', 'active'),
('LearningAgent', 'Performance — Strategy Recommendations (Read-only)', 'active'),
('SupervisorAgent', 'Supervisor — System Health & Coordinator', 'active')
ON CONFLICT (name) DO UPDATE SET status = 'active';
