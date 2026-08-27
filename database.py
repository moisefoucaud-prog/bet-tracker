import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get('DB_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bets.db'))

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match TEXT NOT NULL,
            league TEXT,
            date TEXT,
            home_team TEXT,
            away_team TEXT,
            suggested_odds REAL,
            kelly_stake REAL,
            filters_json TEXT,
            status TEXT DEFAULT 'pending' CHECK(status IN (''pending'',''validated'',''ignored'')),
            created_at TEXT DEFAULT (datetime(''now''))
        );
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER,
            match TEXT NOT NULL,
            league TEXT,
            date TEXT,
            home_team TEXT,
            away_team TEXT,
            suggested_odds REAL,
            actual_odds REAL,
            stake REAL,
            bookmaker TEXT,
            status TEXT DEFAULT ''open'' CHECK(status IN (''open'',''won'',''lost'',''void'')),
            profit REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime(''now'')),
            closed_at TEXT,
            FOREIGN KEY (signal_id) REFERENCES signals(id)
        );
        CREATE TABLE IF NOT EXISTS bankroll (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            updated_at TEXT DEFAULT (datetime(''now''))
        );
    ''')
    row = conn.execute("SELECT COUNT(*) as c FROM bankroll").fetchone()
    if row['c'] == 0:
        conn.execute("INSERT INTO bankroll (amount) VALUES (?)", (1000.0,))
    conn.commit()
    conn.close()