import os
import json
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bets.db')


class DBAdapter:
    def __init__(self):
        self.db_url = os.environ.get('DATABASE_URL')
        self.is_postgres = bool(self.db_url)

    def placeholder(self):
        return '%s' if self.is_postgres else '?'

    def get_conn(self):
        if self.is_postgres:
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(self.db_url)
            conn.autocommit = False
            return conn
        else:
            import sqlite3
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            return conn

    def fetchall_dict(self, cursor):
        if self.is_postgres:
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        else:
            return [dict(row) for row in cursor.fetchall()]

    def fetchone_dict(self, cursor):
        if self.is_postgres:
            row = cursor.fetchone()
            if row is None:
                return None
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        else:
            row = cursor.fetchone()
            if row is None:
                return None
            return dict(row)


db = DBAdapter()


def get_db():
    return db.get_conn()


def init_db():
    conn = get_db()
    p = db.placeholder()

    if db.is_postgres:
        cur = conn.cursor()
        cur.execute('''
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
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending','validated','ignored')),
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        cur.execute('''
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
                status TEXT DEFAULT 'open' CHECK(status IN ('open','won','lost','void')),
                profit REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                closed_at TIMESTAMP,
                FOREIGN KEY (signal_id) REFERENCES signals(id)
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bankroll (
                id SERIAL PRIMARY KEY,
                amount REAL NOT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        conn.commit()

        # Initialize bankroll if empty
        cur.execute("SELECT COUNT(*) as c FROM bankroll")
        row = cur.fetchone()
        if row[0] == 0:
            cur.execute(f"INSERT INTO bankroll (amount) VALUES ({p})", (1000.0,))
            conn.commit()
        cur.close()
    else:
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
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending','validated','ignored')),
                created_at TEXT DEFAULT (datetime('now'))
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
                status TEXT DEFAULT 'open' CHECK(status IN ('open','won','lost','void')),
                profit REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                closed_at TEXT,
                FOREIGN KEY (signal_id) REFERENCES signals(id)
            );

            CREATE TABLE IF NOT EXISTS bankroll (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );
        ''')

        # Initialize bankroll if empty
        row = conn.execute("SELECT COUNT(*) as c FROM bankroll").fetchone()
        if row['c'] == 0:
            conn.execute("INSERT INTO bankroll (amount) VALUES (?)", (1000.0,))

        conn.commit()

    conn.close()


def seed_demo_data():
    conn = get_db()
    p = db.placeholder()

    if db.is_postgres:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as c FROM bets")
        row = cur.fetchone()
        if row[0] > 0:
            cur.close()
            conn.close()
            return
    else:
        row = conn.execute("SELECT COUNT(*) as c FROM bets").fetchone()
        if row['c'] > 0:
            conn.close()
            return

    now = datetime.now()
    demo_bets = [
        {
            "match": "Lyon vs Le Havre",
            "league": "Ligue 1",
            "date": (now - timedelta(days=14)).strftime("%Y-%m-%dT15:00:00"),
            "home_team": "Lyon",
            "away_team": "Le Havre",
            "suggested_odds": 1.51,
            "actual_odds": 1.48,
            "stake": 15.0,
            "bookmaker": "Betclic",
            "status": "won",
            "profit": 7.20,
        },
        {
            "match": "PSG vs Marseille",
            "league": "Ligue 1",
            "date": (now - timedelta(days=12)).strftime("%Y-%m-%dT21:00:00"),
            "home_team": "PSG",
            "away_team": "Marseille",
            "suggested_odds": 1.35,
            "actual_odds": 1.33,
            "stake": 20.0,
            "bookmaker": "Unibet",
            "status": "won",
            "profit": 6.60,
        },
        {
            "match": "Inter vs Juventus",
            "league": "Serie A",
            "date": (now - timedelta(days=10)).strftime("%Y-%m-%dT20:45:00"),
            "home_team": "Inter",
            "away_team": "Juventus",
            "suggested_odds": 1.72,
            "actual_odds": 1.70,
            "stake": 12.0,
            "bookmaker": "Bet365",
            "status": "lost",
            "profit": -12.0,
        },
        {
            "match": "Bayern vs Dortmund",
            "league": "Bundesliga",
            "date": (now - timedelta(days=8)).strftime("%Y-%m-%dT18:30:00"),
            "home_team": "Bayern",
            "away_team": "Dortmund",
            "suggested_odds": 1.45,
            "actual_odds": 1.44,
            "stake": 18.0,
            "bookmaker": "Winamax",
            "status": "won",
            "profit": 7.92,
        },
        {
            "match": "Napoli vs Roma",
            "league": "Serie A",
            "date": (now - timedelta(days=6)).strftime("%Y-%m-%dT20:45:00"),
            "home_team": "Napoli",
            "away_team": "Roma",
            "suggested_odds": 1.58,
            "actual_odds": 1.55,
            "stake": 14.0,
            "bookmaker": "Betclic",
            "status": "won",
            "profit": 7.70,
        },
        {
            "match": "Monaco vs Lille",
            "league": "Ligue 1",
            "date": (now - timedelta(days=4)).strftime("%Y-%m-%dT17:00:00"),
            "home_team": "Monaco",
            "away_team": "Lille",
            "suggested_odds": 1.62,
            "actual_odds": 1.60,
            "stake": 13.0,
            "bookmaker": "Unibet",
            "status": "lost",
            "profit": -13.0,
        },
        {
            "match": "Leipzig vs Frankfurt",
            "league": "Bundesliga",
            "date": (now - timedelta(days=2)).strftime("%Y-%m-%dT15:30:00"),
            "home_team": "Leipzig",
            "away_team": "Frankfurt",
            "suggested_odds": 1.40,
            "actual_odds": 1.42,
            "stake": 16.0,
            "bookmaker": "Bet365",
            "status": "won",
            "profit": 6.72,
        },
        {
            "match": "Nice vs Rennes",
            "league": "Ligue 1",
            "date": (now + timedelta(days=1)).strftime("%Y-%m-%dT15:00:00"),
            "home_team": "Nice",
            "away_team": "Rennes",
            "suggested_odds": 1.55,
            "actual_odds": 1.53,
            "stake": 14.0,
            "bookmaker": "Winamax",
            "status": "open",
            "profit": 0,
        },
        {
            "match": "Milan vs Atalanta",
            "league": "Serie A",
            "date": (now + timedelta(days=2)).strftime("%Y-%m-%dT20:45:00"),
            "home_team": "Milan",
            "away_team": "Atalanta",
            "suggested_odds": 1.68,
            "actual_odds": 1.65,
            "stake": 11.0,
            "bookmaker": "Betclic",
            "status": "open",
            "profit": 0,
        },
    ]

    if db.is_postgres:
        cur = conn.cursor()
        # Update bankroll history based on demo bets
        bankroll = 1000.0
        for bet in demo_bets:
            created = (now - timedelta(days=15)).strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(f'''
                INSERT INTO bets (match, league, date, home_team, away_team,
                    suggested_odds, actual_odds, stake, bookmaker, status, profit, created_at, closed_at)
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
            ''', (
                bet['match'], bet['league'], bet['date'], bet['home_team'], bet['away_team'],
                bet['suggested_odds'], bet['actual_odds'], bet['stake'], bet['bookmaker'],
                bet['status'], bet['profit'], created,
                now.strftime("%Y-%m-%d %H:%M:%S") if bet['status'] != 'open' else None
            ))
            if bet['status'] in ('won', 'lost'):
                bankroll += bet['profit']

        # Record bankroll history
        cur.execute(f"UPDATE bankroll SET amount = {p} WHERE id = 1", (bankroll,))

        # Add bankroll history points
        running = 1000.0
        for i, bet in enumerate(demo_bets):
            if bet['status'] in ('won', 'lost'):
                running += bet['profit']
                ts = (now - timedelta(days=14-i*2)).strftime("%Y-%m-%d %H:%M:%S")
                cur.execute(f"INSERT INTO bankroll (amount, updated_at) VALUES ({p}, {p})", (running, ts))

        # Add a pending signal for demo
        cur.execute(f'''
            INSERT INTO signals (match, league, date, home_team, away_team, suggested_odds, kelly_stake, filters_json, status)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, 'pending')
        ''', (
            "Lens vs Strasbourg", "Ligue 1", (now + timedelta(days=3)).strftime("%Y-%m-%dT15:00:00"),
            "Lens", "Strasbourg", 1.48, 16.5,
            json.dumps({"form": "4/5", "hst_ratio": "5.8 > 5.0", "odds_range": "1.40-1.60"})
        ))

        conn.commit()
        cur.close()
    else:
        # Update bankroll history based on demo bets
        bankroll = 1000.0
        for bet in demo_bets:
            created = (now - timedelta(days=15)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute('''
                INSERT INTO bets (match, league, date, home_team, away_team,
                    suggested_odds, actual_odds, stake, bookmaker, status, profit, created_at, closed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                bet['match'], bet['league'], bet['date'], bet['home_team'], bet['away_team'],
                bet['suggested_odds'], bet['actual_odds'], bet['stake'], bet['bookmaker'],
                bet['status'], bet['profit'], created,
                now.strftime("%Y-%m-%d %H:%M:%S") if bet['status'] != 'open' else None
            ))
            if bet['status'] in ('won', 'lost'):
                bankroll += bet['profit']

        # Record bankroll history
        conn.execute("UPDATE bankroll SET amount = ? WHERE id = 1", (bankroll,))

        # Add bankroll history points
        running = 1000.0
        for i, bet in enumerate(demo_bets):
            if bet['status'] in ('won', 'lost'):
                running += bet['profit']
                ts = (now - timedelta(days=14-i*2)).strftime("%Y-%m-%d %H:%M:%S")
                conn.execute("INSERT INTO bankroll (amount, updated_at) VALUES (?, ?)", (running, ts))

        # Add a pending signal for demo
        conn.execute('''
            INSERT INTO signals (match, league, date, home_team, away_team, suggested_odds, kelly_stake, filters_json, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        ''', (
            "Lens vs Strasbourg", "Ligue 1", (now + timedelta(days=3)).strftime("%Y-%m-%dT15:00:00"),
            "Lens", "Strasbourg", 1.48, 16.5,
            json.dumps({"form": "4/5", "hst_ratio": "5.8 > 5.0", "odds_range": "1.40-1.60"})
        ))

        conn.commit()

    conn.close()
