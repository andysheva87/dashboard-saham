-- SQLite schema for V5 Mobile Swing Hunter
-- The app creates these tables automatically on first run.
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS app_settings (setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, txn_time TEXT NOT NULL, symbol TEXT NOT NULL, txn_type TEXT NOT NULL CHECK(txn_type IN ('BUY','SELL','OPENING')), lots INTEGER NOT NULL CHECK(lots>0), price REAL NOT NULL CHECK(price>0), gross_amount REAL NOT NULL, fee_amount REAL NOT NULL DEFAULT 0, realized_pnl REAL, notes TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_txn_symbol_time ON transactions(symbol,txn_time);
CREATE INDEX IF NOT EXISTS idx_txn_time ON transactions(txn_time);
CREATE TABLE IF NOT EXISTS holdings (symbol TEXT PRIMARY KEY, shares INTEGER NOT NULL DEFAULT 0, avg_cost_per_share REAL NOT NULL DEFAULT 0, total_cost REAL NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS risk_limits (id INTEGER PRIMARY KEY CHECK(id=1), risk_per_trade_pct REAL NOT NULL DEFAULT 1, max_position_pct REAL NOT NULL DEFAULT 25, max_drawdown_pct REAL NOT NULL DEFAULT 10, portfolio_reference_value REAL NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS equity_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_date TEXT NOT NULL UNIQUE, realized_pnl REAL NOT NULL DEFAULT 0, unrealized_pnl REAL NOT NULL DEFAULT 0, equity_value REAL NOT NULL DEFAULT 0, note TEXT);
