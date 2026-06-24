-- SPY Trader PostgreSQL Schema
-- Run this to initialize the database

-- Signals table (main trading signals)
CREATE TABLE IF NOT EXISTS signals (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    signal VARCHAR(50),
    signal_type VARCHAR(50),
    status VARCHAR(50),
    confidence INT,
    spy_price DECIMAL(10,2),
    qqq_price DECIMAL(10,2),
    add_value DECIMAL(10,2),
    macd_dir VARCHAR(10),
    rev_score INT,
    rev_dir VARCHAR(50),
    st_flip BOOLEAN,
    tl_break VARCHAR(10),
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Paper trades (auto-trade records)
CREATE TABLE IF NOT EXISTS paper_trades (
    id SERIAL PRIMARY KEY,
    entry_time TIMESTAMP NOT NULL,
    exit_time TIMESTAMP,
    direction VARCHAR(10),
    entry_price DECIMAL(10,2),
    exit_price DECIMAL(10,2),
    signal_type VARCHAR(50),
    conf_score INT,
    pnl DECIMAL(10,3),
    pnl_percent DECIMAL(10,3),
    is_win BOOLEAN,
    closed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Manual trades (user-initiated trades)
CREATE TABLE IF NOT EXISTS manual_trades (
    id BIGINT PRIMARY KEY,
    entry_date DATE,
    entry_time TIME,
    entry_price DECIMAL(10,2),
    exit_price DECIMAL(10,2),
    direction VARCHAR(10),
    signal VARCHAR(50),
    conf_score INT,
    pnl DECIMAL(10,3),
    pnl_percent DECIMAL(10,3),
    is_win BOOLEAN,
    closed BOOLEAN DEFAULT FALSE,
    snapshot JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Trendline breaks (LuxAlgo indicator signals)
CREATE TABLE IF NOT EXISTS trendline_breaks (
    id SERIAL PRIMARY KEY,
    date DATE,
    time TIME,
    symbol VARCHAR(10),
    direction VARCHAR(10),
    price DECIMAL(10,2),
    is_manual BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- System status (bot health check)
CREATE TABLE IF NOT EXISTS system_status (
    id SERIAL PRIMARY KEY,
    bot_running BOOLEAN,
    last_update TIMESTAMP,
    stale BOOLEAN,
    chrome_pid INT,
    tv_pid INT,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signals_signal ON signals(signal);
CREATE INDEX IF NOT EXISTS idx_paper_trades_entry ON paper_trades(entry_time DESC);
CREATE INDEX IF NOT EXISTS idx_paper_trades_closed ON paper_trades(closed);
CREATE INDEX IF NOT EXISTS idx_trendline_breaks_date ON trendline_breaks(date DESC);
CREATE INDEX IF NOT EXISTS idx_trendline_breaks_symbol ON trendline_breaks(symbol);
CREATE INDEX IF NOT EXISTS idx_manual_trades_date ON manual_trades(entry_date DESC);

-- Grant permissions (if using restricted user)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO your_user;
