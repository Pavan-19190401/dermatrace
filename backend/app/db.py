import os, sqlite3
DATA = os.environ.get("DT_DATA", os.path.join(os.path.dirname(__file__), "..", "data"))
os.makedirs(os.path.join(DATA, "img"), exist_ok=True)
def conn():
    c = sqlite3.connect(os.path.join(DATA, "dermatrace.db")); c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); return c
def init():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw TEXT NOT NULL, created REAL);
        CREATE TABLE IF NOT EXISTS lesions(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, name TEXT NOT NULL, site TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS visits(id INTEGER PRIMARY KEY, lesion_id INTEGER NOT NULL REFERENCES lesions(id) ON DELETE CASCADE, file TEXT NOT NULL, taken REAL, metrics TEXT, note TEXT);
        CREATE TABLE IF NOT EXISTS results(id INTEGER PRIMARY KEY, lesion_id INTEGER, visit_a INTEGER, visit_b INTEGER, score INTEGER, verdict INTEGER, conf INTEGER, created REAL);
        """)
