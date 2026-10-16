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
  map_votes   upvotes on shared Music Maps (one row per listener per map)
  follows     who follows whom (usernames)
  events      what people did, for the feed (shared a map, a fix was agreed, ...)
  atlas_pins  notes people pinned on songs in the community atlas
  artist_tracks  songs artists uploaded to see where they land on the atlas
  radio_plays stations people started, for the radio charts
  quiz_scores rounds of the music quiz, for its leaderboard
  jobs        stem, MIDI and CSV jobs and their results, so a restart keeps them
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
CREATE TABLE IF NOT EXISTS map_votes (
    share_id TEXT NOT NULL,
    voter TEXT NOT NULL,          -- "user:<name>" or "anon:<browser id>"
    ip_hash TEXT,
    created_at REAL NOT NULL,
    PRIMARY KEY (share_id, voter)
);
CREATE INDEX IF NOT EXISTS map_votes_ip ON map_votes (share_id, ip_hash);
CREATE TABLE IF NOT EXISTS follows (
    follower TEXT NOT NULL,
    followee TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (follower, followee)
);
CREATE INDEX IF NOT EXISTS follows_followee ON follows (followee);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,          -- username, or "" for the system
    kind TEXT NOT NULL,           -- shared_map, followed, upvoted, fix_agreed, pinned, artist_track, compared
    target TEXT,                  -- username the event is about (gets it in their feed too)
    payload TEXT NOT NULL,        -- JSON
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS events_actor ON events (actor, created_at);
CREATE INDEX IF NOT EXISTS events_target ON events (target, created_at);
CREATE TABLE IF NOT EXISTS atlas_pins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_key TEXT NOT NULL,
    author TEXT NOT NULL,         -- "user:<name>" or "anon:<browser id>"
    text TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS atlas_pins_song ON atlas_pins (song_key);
CREATE TABLE IF NOT EXISTS artist_tracks (
    id TEXT PRIMARY KEY,
    owner TEXT,                   -- username, or NULL when uploaded signed out
    title TEXT NOT NULL,
    artist TEXT,
    result TEXT NOT NULL,         -- JSON: where it landed
    public INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS radio_plays (
    station TEXT NOT NULL,        -- stable key, e.g. "share:<id>:cluster:3"
    label TEXT NOT NULL,
    share_id TEXT,
    listener TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS radio_plays_time ON radio_plays (created_at);
CREATE TABLE IF NOT EXISTS quiz_scores (
    listener TEXT NOT NULL,
    name TEXT,
    score INTEGER NOT NULL,
    rounds INTEGER NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS quiz_scores_time ON quiz_scores (created_at);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    data TEXT NOT NULL,           -- JSON: the whole job, as the API returns it
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_time ON jobs (updated_at);
"""

# Columns added after a table first shipped: (table, column, definition)
_COLUMNS = [
    ("users", "display_name", "TEXT"),
    ("users", "bio", "TEXT"),
    ("users", "library_csv", "TEXT"),   # the library behind "my map", for the digest and compare
    ("users", "library_title", "TEXT"),
    ("users", "is_artist", "INTEGER NOT NULL DEFAULT 0"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    for table, col, decl in _COLUMNS:
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if col not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

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
                _migrate(conn)
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
