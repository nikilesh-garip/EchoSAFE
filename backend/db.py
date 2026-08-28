"""SQLite access and schema migrations shared by main.py and emergency_routes.py.

Extracted from main.py when the escalation layer was added: the emergency
router needs the same connection helper, and duplicating it would have meant
two places that could drift on connection cleanup.
"""

import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get(
    "ECHO_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "echo_backend.db"),
)

# Evidence clips (the 5 seconds of audio that triggered an incident) live
# outside the DB so they can be streamed to Telegram/Twilio without loading
# them into memory twice.
EVIDENCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evidence")


@contextmanager
def get_db():
    """Context manager to prevent SQLite connection leaks under runtime exceptions."""
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def _columns(cursor, table):
    cursor.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def _add_column_if_missing(cursor, table, column, ddl):
    if column not in _columns(cursor, table):
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db():
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                class_name TEXT NOT NULL,
                primary_conf REAL NOT NULL,
                verification_conf REAL NOT NULL,
                risk_score INTEGER NOT NULL,
                risk_level TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                relation TEXT
            )
        """)

        # Escalation routing lives on the contact: which channels that person
        # accepts, and in what order they are tried. Added by migration so an
        # existing echo_backend.db keeps its rows.
        _add_column_if_missing(cursor, "contacts", "telegram_chat_id", "TEXT")
        _add_column_if_missing(cursor, "contacts", "priority", "INTEGER DEFAULT 100")
        _add_column_if_missing(cursor, "contacts", "notify_call", "INTEGER DEFAULT 1")
        _add_column_if_missing(cursor, "contacts", "notify_telegram", "INTEGER DEFAULT 1")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                class_name TEXT NOT NULL,
                raw_class TEXT,
                profile TEXT DEFAULT 'real',
                primary_conf REAL DEFAULT 0.0,
                verification_conf REAL DEFAULT 0.0,
                risk_score INTEGER DEFAULT 0,
                risk_level TEXT DEFAULT 'NORMAL',
                latitude REAL,
                longitude REAL,
                accuracy_m REAL,
                place_label TEXT,
                clip_path TEXT,
                clip_seconds REAL,
                state TEXT NOT NULL,
                cancel_deadline REAL,
                dispatched_at REAL,
                cancelled_at REAL,
                note TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS escalation_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL,
                contact_id INTEGER,
                contact_name TEXT,
                channel TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT,
                created_at REAL NOT NULL
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_attempts_incident ON escalation_attempts(incident_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_incidents_user ON incidents(user_id, created_at DESC)"
        )
        conn.commit()
