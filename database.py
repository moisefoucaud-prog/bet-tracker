import os
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

DATABASE_URL = os.environ.get('DATABASE_URL', '')

if DATABASE_URL:
    # Fix Render postgres:// prefix
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = 'postgresql://' + DATABASE_URL[len('postgres://'):]
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bets.db')
    engine = create_engine(f'sqlite:///{DB_PATH}', connect_args={'check_same_thread': False}, poolclass=StaticPool)

IS_POSTGRES = bool(os.environ.get('DATABASE_URL', ''))


def get_db():
    return engine.connect()


def init_db():
    with engine.connect() as conn:
        if IS_POSTGRES:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS signals (
                    id SERIAL PRIMARY KEY, match TEXT NOT NULL, league TEXT,
                    date TEXT, home_team TEXT, away_team TEXT,
                    suggested_odds REAL, kelly_stake REAL, filters_json TEXT,
                    status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT NOW())
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS bets (
                    id SERIAL PRIMARY KEY, signal_id INTEGER, match TEXT NOT NULL,
                    league TEXT, date TEXT, home_team TEXT, away_team TEXT,
                    suggested_odds REAL, actual_odds REAL, stake REAL, bookmaker TEXT,
                    status TEXT DEFAULT 'open', profit REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(), closed_at TIMESTAMP)
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS bankroll (
                    id SERIAL PRIMARY KEY, amount REAL NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW())
            """))
            result = conn.execute(text('SELECT COUNT(*) FROM bankroll'))
            if result.scalar() == 0:
                conn.execute(text('INSERT INTO bankroll (amount) VALUES (1000.0)'))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, match TEXT NOT NULL, league TEXT,
                    date TEXT, home_team TEXT, away_team TEXT, suggested_odds REAL,
                    kelly_stake REAL, filters_json TEXT, status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT (datetime('now')))
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS bets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, signal_id INTEGER,
                    match TEXT NOT NULL, league TEXT, date TEXT, home_team TEXT,
                    away_team TEXT, suggested_odds REAL, actual_odds REAL, stake REAL,
                    bookmaker TEXT, status TEXT DEFAULT 'open', profit REAL DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')), closed_at TEXT)
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS bankroll (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, amount REAL NOT NULL,
                    updated_at TEXT DEFAULT (datetime('now')))
            """))
            result = conn.execute(text('SELECT COUNT(*) FROM bankroll'))
            if result.scalar() == 0:
                conn.execute(text('INSERT INTO bankroll (amount) VALUES (1000.0)'))
        conn.commit()
