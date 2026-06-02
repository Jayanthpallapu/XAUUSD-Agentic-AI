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

-- Seed Agent Registry
INSERT INTO agent_registry (name, role, status) VALUES
('CorrelationAgent', 'Correlated Pairs & News Analyst', 'active'),
('NewsAgent', 'XAUUSD News & Impact Analyst', 'active'),
('TradingAgent', 'Price Reaction Observer & Signal Generator', 'active'),
('QAAgent', 'Quality Assurance & Improvement Analyst', 'active'),
('PerformanceAgent', 'Trade Observability & Accuracy Tracker', 'active'),
('SupervisorAgent', 'Chief AI Officer — System Supervisor', 'active')
ON CONFLICT (name) DO UPDATE SET status = 'active';
