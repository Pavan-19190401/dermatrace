"""DermaTrace Universal Database Layer.
Supports:
1. PostgreSQL (via DATABASE_URL on Render, Supabase, Neon, Railway, AWS RDS, etc.)
2. SQLite (default local file data/dermatrace.db)
Both provide an identical context-manager API with dictionary row access and .lastrowid support.
"""
import os, re

DATA = os.environ.get("DT_DATA", os.path.join(os.path.dirname(__file__), "..", "data"))
os.makedirs(os.path.join(DATA, "img"), exist_ok=True)
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# Normalize postgres:// to postgresql:// if needed (e.g. from Render or Heroku)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

class PGCursorWrapper:
    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        r = self._cursor.fetchone()
        return dict(r) if r is not None else None

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [dict(r) for r in rows]

    def __iter__(self):
        for r in self._cursor:
            yield dict(r)

class PGConnectionWrapper:
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        self._conn.close()

    def execute(self, sql, params=()):
        # Convert SQLite '?' parameter syntax to PostgreSQL '%s'
        pg_sql = sql.replace("?", "%s")
        is_insert = bool(re.match(r"^\s*INSERT\s+INTO\s+", pg_sql, re.IGNORECASE))
        
        lastrowid = None
        import psycopg2.extras
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        if is_insert and "RETURNING" not in pg_sql.upper():
            pg_sql = pg_sql.rstrip().rstrip(";") + " RETURNING id;"
            cur.execute(pg_sql, params)
            ret = cur.fetchone()
            if ret and "id" in ret:
                lastrowid = ret["id"]
        else:
            cur.execute(pg_sql, params)
            
        return PGCursorWrapper(cur, lastrowid=lastrowid)

    def executescript(self, script):
        with self._conn.cursor() as cur:
            cur.execute(script)

class SQLiteWrapper:
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        self._conn.close()

    def execute(self, sql, params=()):
        return self._conn.execute(sql, params)

    def executescript(self, script):
        return self._conn.executescript(script)

def is_postgres():
    return bool(DATABASE_URL and DATABASE_URL.startswith("postgresql"))

def conn():
    if is_postgres():
        import psycopg2
        raw = psycopg2.connect(DATABASE_URL)
        return PGConnectionWrapper(raw)
    else:
        import sqlite3
        c = sqlite3.connect(os.path.join(DATA, "dermatrace.db"))
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        return SQLiteWrapper(c)

def init():
    if is_postgres():
        with conn() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS users(
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                pw TEXT NOT NULL,
                role VARCHAR(32) DEFAULT 'client',
                created DOUBLE PRECISION
            );
            CREATE TABLE IF NOT EXISTS lesions(
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                site VARCHAR(255),
                created DOUBLE PRECISION
            );
            CREATE TABLE IF NOT EXISTS visits(
                id SERIAL PRIMARY KEY,
                lesion_id INTEGER NOT NULL REFERENCES lesions(id) ON DELETE CASCADE,
                file VARCHAR(255) NOT NULL,
                taken DOUBLE PRECISION,
                metrics TEXT,
                note TEXT
            );
            CREATE TABLE IF NOT EXISTS results(
                id SERIAL PRIMARY KEY,
                lesion_id INTEGER,
                visit_a INTEGER,
                visit_b INTEGER,
                score INTEGER,
                verdict INTEGER,
                conf INTEGER,
                created DOUBLE PRECISION
            );
            """)
            try:
                c.execute("ALTER TABLE users ADD COLUMN role VARCHAR(32) DEFAULT 'client';")
            except Exception:
                pass
    else:
        with conn() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw TEXT NOT NULL, role TEXT DEFAULT 'client', created REAL);
            CREATE TABLE IF NOT EXISTS lesions(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, name TEXT NOT NULL, site TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS visits(id INTEGER PRIMARY KEY, lesion_id INTEGER NOT NULL REFERENCES lesions(id) ON DELETE CASCADE, file TEXT NOT NULL, taken REAL, metrics TEXT, note TEXT);
            CREATE TABLE IF NOT EXISTS results(id INTEGER PRIMARY KEY, lesion_id INTEGER, visit_a INTEGER, visit_b INTEGER, score INTEGER, verdict INTEGER, conf INTEGER, created REAL);
            """)
            try:
                c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'client';")
            except Exception:
                pass
