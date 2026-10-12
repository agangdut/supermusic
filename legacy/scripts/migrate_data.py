"""
Create/refresh a lightweight SQLite database from CSV(s) in data/datasets/.
- Reads sample_dataset.csv (and any *.csv you add).
- Normalizes into artists, albums, tracks tables with FKs.
- Validates basic fields and deduplicates artists/albums.
- Idempotent: re-runs safely; will upsert by (title, artist, album).

Usage:
  python scripts/migrate_data.py
"""

from __future__ import annotations
import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASETS_DIR = ROOT / "data" / "datasets"
DB_PATH = ROOT / "data" / "supermusic.db"

DATASETS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS artists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    artist_id INTEGER NOT NULL,
    UNIQUE(title, artist_id),
    FOREIGN KEY (artist_id) REFERENCES artists(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_ext_id TEXT,                 -- optional external id (csv track_id)
    title TEXT NOT NULL,
    artist_id INTEGER NOT NULL,
    album_id INTEGER,
    genre TEXT,
    duration_sec INTEGER,
    bpm INTEGER,
    key TEXT,
    youtube_url TEXT,
    local_path TEXT,
    UNIQUE(title, artist_id, COALESCE(album_id, -1)),
    FOREIGN KEY (artist_id) REFERENCES artists(id) ON DELETE CASCADE,
    FOREIGN KEY (album_id) REFERENCES albums(id) ON DELETE SET NULL
);
"""

def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()

def upsert_artist(conn: sqlite3.Connection, name: str) -> int:
    cur = conn.execute("INSERT OR IGNORE INTO artists(name) VALUES (?)", (name,))
    if cur.lastrowid:
        return cur.lastrowid
    # fetch existing
    row = conn.execute("SELECT id FROM artists WHERE name = ?", (name,)).fetchone()
    return int(row["id"])

def upsert_album(conn: sqlite3.Connection, title: str, artist_id: int) -> int:
    cur = conn.execute(
        "INSERT OR IGNORE INTO albums(title, artist_id) VALUES (?, ?)",
        (title, artist_id),
    )
    if cur.lastrowid:
        return cur.lastrowid
    row = conn.execute(
        "SELECT id FROM albums WHERE title = ? AND artist_id = ?",
        (title, artist_id),
    ).fetchone()
    return int(row["id"])

def upsert_track(
    conn: sqlite3.Connection,
    track_ext_id: str | None,
    title: str,
    artist_id: int,
    album_id: int | None,
    genre: str | None,
    duration_sec: int | None,
    bpm: int | None,
    key: str | None,
    youtube_url: str | None,
    local_path: str | None,
) -> int:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO tracks
        (track_ext_id, title, artist_id, album_id, genre, duration_sec, bpm, key, youtube_url, local_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (track_ext_id, title, artist_id, album_id, genre, duration_sec, bpm, key, youtube_url, local_path),
    )
    if cur.lastrowid:
        return cur.lastrowid
    row = conn.execute(
        """
        SELECT id FROM tracks
        WHERE title = ? AND artist_id = ? AND COALESCE(album_id, -1) = COALESCE(?, -1)
        """,
        (title, artist_id, album_id),
    ).fetchone()
    return int(row["id"])

def parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None

def load_csvs():
    csv_files = sorted(DATASETS_DIR.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {DATASETS_DIR}.")
        return

    conn = connect_db()
    with conn:
        apply_schema(conn)

        inserted_tracks = 0
        for csv_path in csv_files:
            print(f"Processing {csv_path.name}...")
            with csv_path.open("r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                required = {"title", "artist"}
                if not required.issubset(set(reader.fieldnames or [])):
                    print(f"  Skipping: missing required columns {required}. Found: {reader.fieldnames}")
                    continue

                for row in reader:
                    title = (row.get("title") or "").strip()
                    artist_name = (row.get("artist") or "").strip()
                    if not title or not artist_name:
                        continue

                    album_title = (row.get("album") or "").strip()
                    genre = (row.get("genre") or "").strip() or None
                    duration_sec = parse_int(row.get("duration_sec"))
                    bpm = parse_int(row.get("bpm"))
                    key = (row.get("key") or "").strip() or None
                    youtube_url = (row.get("youtube_url") or "").strip() or None
                    local_path = (row.get("local_path") or "").strip() or None
                    track_ext_id = (row.get("track_id") or "").strip() or None

                    artist_id = upsert_artist(conn, artist_name)
                    album_id = None
                    if album_title:
                        album_id = upsert_album(conn, album_title, artist_id)

                    _ = upsert_track(
                        conn,
                        track_ext_id=track_ext_id,
                        title=title,
                        artist_id=artist_id,
                        album_id=album_id,
                        genre=genre,
                        duration_sec=duration_sec,
                        bpm=bpm,
                        key=key,
                        youtube_url=youtube_url,
                        local_path=local_path,
                    )
                    inserted_tracks += 1

        print(f"Done. Processed/Upserted ~{inserted_tracks} track rows across {len(csv_files)} CSV file(s).")
        print(f"SQLite DB at: {DB_PATH}")

if __name__ == "__main__":
    load_csvs()
