"""
The app's saved data: one SQLite file (data/supermusic.db, or SM_DB_PATH).

SQLite is a whole database in a single file, built into Python, so there is
nothing extra to install or run. It survives restarts, unlike the old
in-memory dictionaries.

Tables:
  users       accounts (username, bcrypt password hash, email)
  songs       one row per song anyone has looked up or described (artist, title)
  song_facts  what an online lookup found for a song (BPM, key, energy, ...)
  song_votes  what listeners said a song's stats are (one row per listener per stat)
"""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

from app.core.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    hashed_password TEXT NOT NULL,
    email TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS songs (
    song_key TEXT PRIMARY KEY,
    artist TEXT,
    title TEXT
);
CREATE TABLE IF NOT EXISTS song_facts (
    song_key TEXT NOT NULL,
    field TEXT NOT NULL,
    value TEXT NOT NULL,          -- JSON
    source TEXT,
    updated_at REAL NOT NULL,
    PRIMARY KEY (song_key, field)
);
CREATE TABLE IF NOT EXISTS song_votes (
    song_key TEXT NOT NULL,
    field TEXT NOT NULL,
    voter TEXT NOT NULL,          -- "user:<name>" or "anon:<browser id>"
    ip_hash TEXT,
    value TEXT NOT NULL,          -- JSON
    created_at REAL NOT NULL,
    PRIMARY KEY (song_key, field, voter)
);
CREATE INDEX IF NOT EXISTS song_votes_voter ON song_votes (voter, created_at);
CREATE INDEX IF NOT EXISTS song_votes_ip ON song_votes (ip_hash, created_at);
CREATE INDEX IF NOT EXISTS song_votes_time ON song_votes (created_at);
"""

_local = threading.local()
_init_lock = threading.Lock()
_ready: set = set()


def db_path() -> Path:
    return Path(os.getenv("SM_DB_PATH", "") or (settings.DATA_DIR / "supermusic.db"))


def connect() -> sqlite3.Connection:
    """This thread's connection (SQLite connections shouldn't be shared between threads)."""
    path = str(db_path())
    conns = getattr(_local, "conns", None)
    if conns is None:
        conns = _local.conns = {}
    conn = conns.get(path)
    if conn is None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=30, isolation_level=None)  # autocommit; `with tx()` for batches
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # readers don't wait for a writer
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")  # safe with WAL, and much faster for many small writes
        with _init_lock:
            if path not in _ready:
                conn.executescript(_SCHEMA)
                _ready.add(path)
        conns[path] = conn
    return conn


class tx:
    """`with tx() as c:` runs several writes as one transaction."""

    def __enter__(self) -> sqlite3.Connection:
        self.c = connect()
        self.c.execute("BEGIN IMMEDIATE")
        return self.c

    def __exit__(self, exc_type, exc, tb) -> None:
        self.c.execute("ROLLBACK" if exc_type else "COMMIT")
