"""
The community atlas: one Music Map drawn from every library people listed publicly.

Each listed share that kept its song list adds its songs. Songs in several
libraries appear once, and the number of listeners who have a song stands in
for its play count, so songs many people share glow brighter. No one's play
counts, likes or dates go in: only what the song is (title, artist, genre, key,
tempo, mood, sound).

The atlas is rebuilt in a background thread as soon as a map is shared publicly,
listed, unlisted or deleted (map_share calls `changed()`); until then the last one
is served. Between rebuilds every visit gets the same finished answer, kept in
memory already gzipped (`response_bytes`), so opening the atlas costs the server
almost nothing. As a safety net, a change made some other way (a share folder
copied in by hand) is noticed within REBUILD_EVERY seconds.

People can pin a short note on any star (song). Notes hang off the song, not its
position, so they survive rebuilds.
"""
from __future__ import annotations

import gzip
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from app.core import map_share, store
from app.core.config import settings
from app.core.library_import import song_key
from app.core.music_map import ALIASES, AUDIO_FEATURES, MapOptions, _find, build_map

MAX_SONGS = 20_000
REBUILD_EVERY = 600     # seconds
MAX_PINS_PER_DAY = 30
PIN_LENGTH = 200
KEEP = ("title", "artist", "album", "genre", "key", "mode", "bpm", "year")

_lock = threading.Lock()
_build_lock = threading.Lock()  # one build at a time
_building = [False]
_dirty = [False]          # a change arrived while a rebuild was running: build again after
_loaded: Dict[str, Any] = {"mtime": None, "data": None}
_checked = [0.0]          # when the safety-net signature check last ran
_response: Dict[str, Any] = {"key": None, "raw": b"", "gz": b""}


def _dir() -> Path:
    d = settings.DATA_DIR / "atlas"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _signature() -> List[str]:
    return sorted(m["id"] for m in map_share.all_listed() if m.get("has_library"))


def _library_rows(share_id: str) -> Optional[pd.DataFrame]:
    path = map_share.library_path(share_id)
    if not path:
        return None
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    cols = {}
    for f in KEEP:
        c = _find(df, f)
        if c is not None:
            cols[c] = f
    for c in df.columns:
        lc = str(c).lower().strip()
        if lc in AUDIO_FEATURES or lc == "sound":
            cols[c] = lc
    if "title" not in cols.values():
        return None
    out = df[list(cols)].rename(columns=cols)
    out = out.loc[:, ~out.columns.duplicated()]
    out["_key"] = [song_key(a, t) for a, t in zip(out.get("artist", [""] * len(out)), out["title"])]
    return out


def collect() -> tuple:
    """(songs DataFrame with a `listeners` column, {song_key: [share ids]}, share metas used)."""
    frames, owners = [], {}
    used = []
    for meta in map_share.all_listed():
        if not meta.get("has_library"):
            continue
        df = _library_rows(meta["id"])
        if df is None or df.empty:
            continue
        df = df.drop_duplicates("_key")
        for k in df["_key"]:
            owners.setdefault(k, []).append(meta["id"])
        frames.append(df)
        used.append(meta)
    if not frames:
        return pd.DataFrame(), {}, []
    allsongs = pd.concat(frames, ignore_index=True, sort=False)
    # Keep the most complete row per song (most filled-in columns)
    allsongs["_filled"] = allsongs.notna().sum(axis=1)
    allsongs = allsongs.sort_values("_filled", ascending=False).drop_duplicates("_key")
    allsongs["listeners"] = allsongs["_key"].map(lambda k: len(owners.get(k, [])))
    allsongs = allsongs.sort_values(["listeners", "_filled"], ascending=False).head(MAX_SONGS)
    allsongs = allsongs.drop(columns=["_filled"]).reset_index(drop=True)
    return allsongs, owners, used


def _write(name: str, data: Any) -> None:
    """Write a gzipped JSON file in one step, so a reader never sees half of it."""
    tmp = _dir() / f".{name}.{threading.get_ident()}.tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, _dir() / name)


def build() -> Dict[str, Any]:
    """Draw the atlas now and save it."""
    with _build_lock:
        return _build()


def _build() -> Dict[str, Any]:
    songs, owners, used = collect()
    sig = sorted(m["id"] for m in used)
    if len(songs) < 3:
        result: Dict[str, Any] = {"tracks": [], "edges": [], "clusters": [], "hidden_connections": [],
                                  "insights": [], "recommendations": [], "meta": {"count": 0}}
    else:
        keys = songs["_key"].tolist()
        if "sound" in songs.columns:  # kept beside the map (too big to send to browsers)
            vecs = {k: v for k, v in zip(keys, songs["sound"]) if isinstance(v, str) and v}
            _write("sound.json.gz", vecs)
        df = songs.drop(columns=["_key"]).rename(columns={"listeners": "play_count"})
        result = build_map(df, MapOptions(neighbors=4))
        for t, k in zip(result["tracks"], keys):
            t["song_key"] = k
            t["listeners"] = t.pop("plays", None) or len(owners.get(k, []))
        # Popularity on the atlas isn't anyone's taste: no "for you" picks or play insights
        result["recommendations"], result["insights"] = [], []
        result.pop("stats", None)
        for c in result["clusters"]:
            c.pop("listening_share", None)
            c.pop("lift", None)
    names = {m["id"]: {"title": m.get("title"), "by": m.get("by"), "owner": m.get("owner")} for m in used}
    result["meta"] = {**result.get("meta", {}), "source": "community atlas", "built": time.time(),
                      "maps": len(used), "signature": sig, "has_listening_data": False}
    _write("owners.json.gz", {"owners": {k: v for k, v in owners.items()}, "maps": names})
    _write("atlas.json.gz", result)
    return result


def _load(name: str) -> Optional[Dict[str, Any]]:
    p = _dir() / name
    if not p.is_file():
        return None
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _rebuild_later() -> None:
    with _lock:
        if _building[0]:
            _dirty[0] = True
            return
        _building[0] = True
        _dirty[0] = False

    def run():
        try:
            while True:
                try:
                    build()
                except Exception:
                    pass
                with _lock:
                    if not _dirty[0]:
                        _building[0] = False
                        return
                    _dirty[0] = False
        except BaseException:
            _building[0] = False
            raise

    threading.Thread(target=run, daemon=True).start()


def changed() -> None:
    """A map was shared, listed, unlisted or deleted: draw the atlas again (in the background)."""
    _rebuild_later()


def _current() -> Optional[Dict[str, Any]]:
    """The saved atlas, read from disk only when the file is new."""
    p = _dir() / "atlas.json.gz"
    try:
        mtime = p.stat().st_mtime_ns
    except OSError:
        return None
    if _loaded["mtime"] != mtime:
        data = _load("atlas.json.gz")
        if data is None:
            return None
        _loaded.update(mtime=mtime, data=data)
    return _loaded["data"]


def get() -> Dict[str, Any]:
    """The atlas. Built on the spot the first time; afterwards refreshed in the background."""
    current = _current()
    if current is None:
        with _lock:
            current = _current()
            if current is None:
                build()
                current = _current() or {}
        return current
    now = time.time()
    if now - _checked[0] > REBUILD_EVERY:
        _checked[0] = now
        if current.get("meta", {}).get("signature") != _signature():
            _rebuild_later()
    return current


def response_bytes(extra: Dict[str, Any]) -> tuple[bytes, bytes]:
    """The atlas plus `extra` (small, changing fields such as artists' tracks) as JSON,
    plain and gzipped. Made once per atlas version and kept in memory."""
    data = get()
    extra_json = json.dumps(extra, separators=(",", ":"), sort_keys=True)
    building = _building[0]
    key = (_loaded["mtime"], extra_json, building)
    if _response["key"] != key:
        payload = {**data, **extra}
        if building:  # the page says "Updating with new maps…"
            payload["meta"] = {**data.get("meta", {}), "refreshing": True}
        raw = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
        _response.update(key=key, raw=raw, gz=gzip.compress(raw, compresslevel=6))
    return _response["raw"], _response["gz"]


def sound_vectors() -> Dict[str, str]:
    """{song_key: encoded CLAP vector} for atlas songs that have one."""
    return _load("sound.json.gz") or {}


def song_maps(keys: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """{song_key: [{id, title, by}]}: the public maps each song is on."""
    data = _load("owners.json.gz") or {}
    owners, maps = data.get("owners", {}), data.get("maps", {})
    return {k: [{"id": s, **maps.get(s, {})} for s in owners.get(k, [])] for k in keys}


def mine(df: pd.DataFrame) -> List[int]:
    """Atlas star ids for the songs in this library."""
    t_col, a_col = _find(df, "title"), _find(df, "artist")
    if t_col is None:
        return []
    artists = df[a_col] if a_col else [""] * len(df)
    keys = {song_key(a, t) for a, t in zip(artists, df[t_col]) if pd.notna(t)}
    atlas = get()
    return [t["id"] for t in atlas.get("tracks", []) if t.get("song_key") in keys]


# ---- pins -------------------------------------------------------------------------------

def pins(keys: Optional[List[str]] = None, limit: int = 500) -> List[Dict[str, Any]]:
    c = store.connect()
    if keys is None:
        rows = c.execute("SELECT * FROM atlas_pins ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    else:
        marks = ",".join("?" * len(keys)) or "''"
        rows = c.execute(f"SELECT * FROM atlas_pins WHERE song_key IN ({marks}) ORDER BY created_at DESC",
                         keys).fetchall()
    from app.core.social import display_names

    names = display_names([r["author"][5:] for r in rows if r["author"].startswith("user:")])
    out = []
    for r in rows:
        a = r["author"]
        out.append({"id": r["id"], "song_key": r["song_key"], "text": r["text"], "at": r["created_at"],
                    "author": names.get(a[5:], a[5:]) if a.startswith("user:") else "a listener",
                    "username": a[5:] if a.startswith("user:") else None, "voter": a})
    return out


def add_pin(song: str, text: str, author: str) -> Dict[str, Any]:
    text = " ".join(str(text or "").split())[:PIN_LENGTH]
    if not text:
        raise ValueError("Write something to pin.")
    c = store.connect()
    today = c.execute("SELECT COUNT(*) FROM atlas_pins WHERE author = ? AND created_at > ?",
                      (author, time.time() - 86400)).fetchone()[0]
    if today >= MAX_PINS_PER_DAY:
        raise ValueError(f"That's {MAX_PINS_PER_DAY} notes today. Try again tomorrow.")
    cur = c.execute("INSERT INTO atlas_pins (song_key, author, text, created_at) VALUES (?, ?, ?, ?)",
                    (song, author, text, time.time()))
    return {"id": cur.lastrowid, "song_key": song, "text": text}


def delete_pin(pin_id: int, author: str) -> bool:
    cur = store.connect().execute("DELETE FROM atlas_pins WHERE id = ? AND author = ?", (pin_id, author))
    return cur.rowcount > 0
