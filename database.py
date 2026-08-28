import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bets.db')


class DBAdapter:
    def __init__(self):
        raw_url = os.environ.get('DATABASE_URL', '')
        if raw_url.startswith('postgres://'):
            raw_url = 'postgresql://' + raw_url[len('postgres://'):]
        self.db_url = raw_url
        self.is_postgres = bool(raw_url)

    def placeholder(self):
        return '%s' if self.is_postgres else '?'

    def get_conn(self):
        if self.is_postgres:
            import pg8000.native
            # Parse URL: postgresql://user:pass@host/dbname
            url = self.db_url.replace('postgresql://', '')
            if '?' in url:
                url = url.split('?')[0]
            user_pass, host_db = url.split('@', 1)
            user, password = user_pass.split(':', 1)
            if '/' in host_db:
                host, dbname = host_db.split('/', 1)
            else:
                host = host_db; dbname = 'postgres'
            port = 5432
            if ':' in host:
                host, port = host.rsplit(':', 1)
                port = int(port)
            conn = pg8000.native.Connection(user=user, password=password, host=host, port=port, database=dbname, ssl_context=True)
            return conn
        else:
            import sqlite3
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            return conn

    def fetchall_dict(self, cursor_or_result):
        if self.is_postgres:
            # pg8000 native returns list of tuples; we need columns
            if hasattr(cursor_or_result, 'columns'):
                cols = cursor_or_result.columns
                return [dict(zip(cols, row)) for row in cursor_or_result]
            return cursor_or_result
        return [dict(row) for row in cursor_or_result.fetchall()]

    def fetchone_dict(self, cursor):
        if self.is_postgres:
            if hasattr(cursor, 'columns'):
                cols = cursor.columns
                rows = list(cursor)
                return dict(zip(cols, rows[0])) if rows else None
            return cursor
        row = cursor.fetchone()
        return dict(row) if row else None

    def execute(self, conn, sql, params=None):
        """Unified execute that returns rows for pg8000 native or cursor for sqlite."""
        if self.is_postgres:
            if params:
                return conn.run(sql, **{}) if not params else conn.run(sql, *params)
            return conn.run(sql)
        else:
            cur = conn.cursor()
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            return cur


db = DBAdapter()


def get_db():
    return db.get_conn()


def _pg_exec(conn, sql, params=None):
    """Execute SQL on pg8000 native connection."""
    if params:
        return conn.run(sql, *params)
    return conn.run(sql)


def init_db():
    if db.is_postgres:
        import pg8000.native
        conn = get_db()
        _pg_exec(conn, """
            CREATE TABLE IF NOT EXISTS signals (
                id SERIAL PRIMARY KEY, match TEXT NOT NULL, league TEXT,
                date TEXT, home_team TEXT, away_team TEXT,
                suggested_odds REAL, kelly_stake REAL, filters_json TEXT,
                status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT NOW())
        """)
        _pg_exec(conn, """
            CREATE TABLE IF NOT EXISTS bets (
                id SERIAL PRIMARY KEY, signal_id INTEGER, match TEXT NOT NULL,
                league TEXT, date TEXT, home_team TEXT, away_team TEXT,
                suggested_odds REAL, actual_odds REAL, stake REAL, bookmaker TEXT,
                status TEXT DEFAULT 'open', profit REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(), closed_at TIMESTAMP)
        """)
        _pg_exec(conn, """
            CREATE TABLE IF NOT EXISTS bankroll (
                id SERIAL PRIMARY KEY, amount REAL NOT NULL,
                updated_at TIMESTAMP DEFAULT NOW())
        """)
        rows = _pg_exec(conn, 'SELECT COUNT(*) FROM bankroll')
        if rows[0][0] == 0:
            _pg_exec(conn, 'INSERT INTO bankroll (amount) VALUES (1000.0)')
        conn.close()
    else:
        import sqlite3
        conn = get_db()
        conn.execute("""CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, match TEXT NOT NULL,
            league TEXT, date TEXT, home_team TEXT, away_team TEXT,
            suggested_odds REAL, kelly_stake REAL, filters_json TEXT,
            status TEXT DEFAULT 'pending', created_at TEXT DEFAULT (datetime('now')))
        """)
        conn.execute("""CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, signal_id INTEGER,
            match TEXT NOT NULL, league TEXT, date TEXT, home_team TEXT,
            away_team TEXT, suggested_odds REAL, actual_odds REAL,
            stake REAL, bookmaker TEXT, status TEXT DEFAULT 'open',
            profit REAL DEFAULT 0, created_at TEXT DEFAULT (datetime('now')), closed_at TEXT)
        """)
        conn.execute("""CREATE TABLE IF NOT EXISTS bankroll (
            id INTEGER PRIMARY KEY AUTOINCREMENT, amount REAL NOT NULL,
            updated_at TEXT DEFAULT (datetime('now')))
        """)
        conn.commit()
        row = conn.execute('SELECT COUNT(*) as c FROM bankroll').fetchone()
        if row['c'] == 0:
            conn.execute('INSERT INTO bankroll (amount) VALUES (1000.0)')
            conn.commit()
        conn.close()
