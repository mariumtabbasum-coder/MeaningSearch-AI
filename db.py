import sqlite3, json, os
from config import DB_PATH, DOCS_JSON

def conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c

def q(sql, args=(), one=False):
    with conn() as c:
        rows = [dict(r) for r in c.execute(sql, args).fetchall()]
    return (rows[0] if rows else None) if one else rows

def run(sql, args=()):
    with conn() as c:
        return c.execute(sql, args).lastrowid

def init():
    with conn() as c:
        c.executescript("""
CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY AUTOINCREMENT,text TEXT,category TEXT,embedding TEXT);
CREATE TABLE IF NOT EXISTS chats(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER,role TEXT,content TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS searches(id INTEGER PRIMARY KEY AUTOINCREMENT,query TEXT,top_score REAL,results INTEGER,created TEXT DEFAULT CURRENT_TIMESTAMP);""")
        if c.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0 and os.path.exists(DOCS_JSON):
            for d in json.load(open(DOCS_JSON, encoding="utf-8")):
                c.execute("INSERT INTO documents(text,category) VALUES(?,?)", (d["text"], d.get("category", "General")))

def load_sample():
    with conn() as c:
        for x in json.load(open(DOCS_JSON, encoding="utf-8")):
            c.execute("INSERT INTO documents(text,category) VALUES(?,?)", (x["text"], x.get("category", "General")))
