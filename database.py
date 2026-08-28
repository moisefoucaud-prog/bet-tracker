import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bets.db')


class DBAdapter:
    def __init__(self):
        raw_url = os.environ.get('DATABASE_URL', '')
        # Render uses postgres:// prefix, psycopg2 needs postgresql://
        if raw_url.startswith('postgres://'):
            raw_url = 'postgresql://' + raw_url[len('postgres://'):]
        # Add sslmode for external connections
        if raw_url and 'sslmode' not in raw_url:
            sep = '&' if '?' in raw_url else '?'
            raw_url += sep + 'sslmode=require'
        self.db_url = raw_url
        self.is_postgres = bool(raw_url)

    def placeholder(self):
        return '%s' if self.is_postgres else '?'

    def get_conn(self):
        if self.is_postgres:
            import psycopg2
            return psycopg2.connect(self.db_url)
        else:
            import sqlite3
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            return conn

    def fetchall_dict(self, cursor):
        if self.is_postgres:
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]
        return [dict(row) for row in cursor.fetchall()]

    def fetchone_dict(self, cursor):
        if self.is_postgres:
            row = cursor.fetchone()
            if row is None: return None
            cols = [d[0] for d in cursor.description]
            return dict(zip(cols, row))
        row = cursor.fetchone()
        return dict(row) if row else None


db = DBAdapter()


def get_db():
    return db.get_conn()


def init_db():
    conn = get_db()
    cur = conn.cursor()
    if db.is_postgres:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id SERIAL PRIMARY KEY,
                match TEXT NOT NULL,
                league TEXT,
                date TEXT,
                home_team TEXT,
                away_team TEXT,
                suggested_odds REAL,
                kelly_stake REAL,
                filters_json TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bets (
                id SERIAL PRIMARY KEY,
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
                status TEXT DEFAULT 'open',
                profit REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                closed_at TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bankroll (
                id SERIAL PRIMARY KEY,
                amount REAL NOT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
        cur.execute('SELECT COUNT(*) FROM bankroll')
        if cur.fetchone()[0] == 0:
            cur.execute('INSERT INTO bankroll (amount) VALUES (1000.0)')
            conn.commit()
    else:
        import sqlite3
        cur.execute("""CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, match TEXT NOT NULL,
            league TEXT, date TEXT, home_team TEXT, away_team TEXT,
            suggested_odds REAL, kelly_stake REAL, filters_json TEXT,
            status TEXT DEFAULT 'pending', created_at TEXT DEFAULT (datetime('now')))
        """)
        cur.execute("""CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, signal_id INTEGER,
            match TEXT NOT NULL, league TEXT, date TEXT, home_team TEXT,
            away_team TEXT, suggested_odds REAL, actual_odds REAL,
            stake REAL, bookmaker TEXT, status TEXT DEFAULT 'open',
            profit REAL DEFAULT 0, created_at TEXT DEFAULT (datetime('now')),
            closed_at TEXT)
        """)
        cur.execute("""CREATE TABLE IF NOT EXISTS bankroll (
            id INTEGER PRIMARY KEY AUTOINCREMENT, amount REAL NOT NULL,
            updated_at TEXT DEFAULT (datetime('now')))
        """)
        conn.commit()
        cur.execute('SELECT COUNT(*) as c FROM bankroll')
        if cur.fetchone()['c'] == 0:
            cur.execute('INSERT INTO bankroll (amount) VALUES (1000.0)')
            conn.commit()
    cur.close()
    conn.close()
