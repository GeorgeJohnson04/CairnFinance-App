"""SQLite access layer. Every table that stores user data carries a
user_id column, and every query in the app filters on it — data isolation
is enforced at the query layer, not the UI.

Schema changes are versioned via PRAGMA user_version so existing databases
(e.g. a user's portable data folder) upgrade in place without data loss."""
import sqlite3

from flask import current_app, g

SCHEMA_VERSION = 2

# Asset types the portfolio understands. Equities/crypto get live prices;
# the rest are manually valued (enter a current value).
ASSET_TYPES = ("Stock", "ETF", "Mutual Fund", "Crypto", "Bond", "Options",
               "Real Estate", "Commodity", "Cash", "Other")
PRICED_ASSET_TYPES = ("Stock", "ETF", "Mutual Fund", "Crypto")

# How often money recurs; used by the planning module to normalize to monthly.
FREQUENCIES = ("weekly", "biweekly", "semimonthly", "monthly",
               "quarterly", "annual")

_AT = ",".join(f"'{t}'" for t in ASSET_TYPES)
_FREQ = ",".join(f"'{t}'" for t in FREQUENCIES)

SCHEMA = f"""
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    pw_hash         TEXT NOT NULL,
    ira_limit       REAL NOT NULL DEFAULT 7500,
    birth_year      INTEGER,
    risk_tolerance  INTEGER NOT NULL DEFAULT 3,
    emergency_months REAL NOT NULL DEFAULT 6,
    employment      TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen   TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT NOT NULL,
    user_agent  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS accounts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN
                  ('brokerage','retirement','cash','savings','other')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, name)
);
CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts(user_id);

CREATE TABLE IF NOT EXISTS holdings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id       INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    asset_type       TEXT NOT NULL CHECK (asset_type IN ({_AT})),
    ticker           TEXT NOT NULL,
    name             TEXT NOT NULL DEFAULT '',
    industry         TEXT NOT NULL DEFAULT '',
    quantity         REAL NOT NULL DEFAULT 0,
    avg_cost         REAL NOT NULL DEFAULT 0,
    current_price    REAL NOT NULL DEFAULT 0,
    price_updated_at TEXT,
    UNIQUE (user_id, account_id, ticker, asset_type)
);
CREATE INDEX IF NOT EXISTS idx_holdings_user ON holdings(user_id);

CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id  INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    trade_date  TEXT NOT NULL,
    asset_type  TEXT NOT NULL CHECK (asset_type IN ({_AT})),
    ticker      TEXT NOT NULL,
    action      TEXT NOT NULL CHECK (action IN ('Buy','Sell')),
    quantity    REAL NOT NULL,
    price       REAL NOT NULL,
    cost_basis  REAL,
    realized_pl REAL,
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_trades_user ON trades(user_id);

CREATE TABLE IF NOT EXISTS incomes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id  INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    income_date TEXT NOT NULL,
    ticker      TEXT NOT NULL DEFAULT '',
    type        TEXT NOT NULL CHECK (type IN
                  ('Interest','Qualified Dividend','Ordinary Dividend','Other')),
    description TEXT NOT NULL DEFAULT '',
    amount      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_incomes_user ON incomes(user_id);

CREATE TABLE IF NOT EXISTS goals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    target_amount REAL NOT NULL,
    saved_amount  REAL NOT NULL DEFAULT 0,
    target_date   TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_goals_user ON goals(user_id);

CREATE TABLE IF NOT EXISTS contributions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id   INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    year         INTEGER NOT NULL,
    amount       REAL NOT NULL,
    contrib_date TEXT NOT NULL,
    note         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_contrib_user ON contributions(user_id);

CREATE TABLE IF NOT EXISTS income_sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'salary',
    amount      REAL NOT NULL,
    frequency   TEXT NOT NULL CHECK (frequency IN ({_FREQ})),
    is_gross    INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_income_sources_user ON income_sources(user_id);

CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'Other',
    amount      REAL NOT NULL,
    frequency   TEXT NOT NULL CHECK (frequency IN ({_FREQ})),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_expenses_user ON expenses(user_id);

CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    snap_date   TEXT NOT NULL,
    total_value REAL NOT NULL,
    cost_basis  REAL NOT NULL DEFAULT 0,
    UNIQUE (user_id, snap_date)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_user ON snapshots(user_id);
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _column_names(db, table):
    return {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}


def _add_column(db, table, coldef):
    col = coldef.split()[0]
    if col not in _column_names(db, table):
        db.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")


def _widen_asset_type(db, table):
    """Rebuild a table whose asset_type CHECK predates the expanded list."""
    row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone()
    if not row or "'Bond'" in row["sql"]:
        return  # already widened (or table absent)
    cols = [r["name"] for r in db.execute(f"PRAGMA table_info({table})")]
    col_list = ", ".join(cols)
    db.execute(f"ALTER TABLE {table} RENAME TO {table}_old")
    db.executescript(SCHEMA)  # recreates {table} with the new CHECK
    db.execute(f"INSERT INTO {table} ({col_list}) "
               f"SELECT {col_list} FROM {table}_old")
    db.execute(f"DROP TABLE {table}_old")


def _migrate(db):
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return

    # v0/v1 -> v2: planning columns, new tables, widened asset types.
    has_users = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if has_users:
        _add_column(db, "users", "birth_year INTEGER")
        _add_column(db, "users", "risk_tolerance INTEGER NOT NULL DEFAULT 3")
        _add_column(db, "users", "emergency_months REAL NOT NULL DEFAULT 6")
        _add_column(db, "users", "employment TEXT NOT NULL DEFAULT ''")
        _widen_asset_type(db, "holdings")
        _widen_asset_type(db, "trades")

    db.executescript(SCHEMA)  # creates any missing tables/indexes
    db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    db.commit()


def init_db(app):
    db = sqlite3.connect(app.config["DATABASE"])
    db.row_factory = sqlite3.Row
    try:
        db.executescript(SCHEMA)
        _migrate(db)
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        db.commit()
    finally:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db(app)
