"""
Turn music-service exports into one track table the Music Map understands.

Supported (detected from the file's columns, so renamed files are fine):

  Spotify
    * Exportify playlist CSVs (track, artists, album, genres, audio features)
    * Account data export: StreamingHistory*.json and the extended
      Streaming_History_Audio_*.json (plays, skips, minutes listened, when
      you first and last played each song), YourLibrary.json (liked songs)
      and Playlist*.json (which of your playlists each song is in)
  Apple Music
    * Library playlist export from the Music app (File > Library > Export
      Playlist…), a tab-separated .txt with Plays / Skips / Genre / Rating
    * privacy.apple.com export: "Apple Music Play Activity.csv",
      "... Track Play History.csv" / "Play History Daily Tracks.csv",
      and "Apple Music Library Tracks.json"
  Anything else with title/artist-style columns (our own CSV template).

Several files can be combined: rows for the same song (matched on artist
and title) are merged, play and skip counts are summed, first/last played
dates widen to cover every file, and features are filled from whichever
file has them.

Optionally, `enrich()` looks each song up online: genre from listener tags
(Last.fm if LASTFM_API_KEY is set, otherwise MusicBrainz; see genres.py),
release year from Deezer's public API (no key needed), and analyses its
30-second preview locally for tempo, key, energy and brightness, so listening histories that
have no audio features still make a meaningful map.
"""
from __future__ import annotations

import io
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.core import genres
from app.core.config import settings

SKIP_MS = 30_000  # a play shorter than 30 s counts as a skip (Spotify's own rule)
CANONICAL = ["title", "artist", "album", "genre", "key", "mode", "bpm", "energy", "danceability", "valence",
             "acousticness", "instrumentalness", "speechiness", "liveness", "loudness", "brightness", "year",
             "play_count", "skip_count", "minutes_played", "first_played", "last_played", "liked", "rating",
             "playlists", "added_at", "uri", "source"]


def _norm(col: str) -> str:
    c = str(col).strip().lower().replace("(s)", "s")
    return re.sub(r"[^a-z0-9]+", "_", c).strip("_")


def _first(df: pd.DataFrame, *names: str) -> Optional[str]:
    for n in names:
        if n in df.columns:
            return n
    return None


def song_key(artist: str, title: str) -> str:
    """Loose match key: lower case, no '(feat. …)', no punctuation."""
    def clean(s: str) -> str:
        s = str(s or "").lower()
        s = re.sub(r"[\(\[](feat|ft|with|prod)[^\)\]]*[\)\]]", "", s)
        s = re.sub(r"\s+-\s+(remaster|live|radio edit|single version).*$", "", s)
        return re.sub(r"[^a-z0-9]+", " ", s).strip()
    first_artist = re.split(r",|;| & | feat\.? | ft\.? ", str(artist or ""), maxsplit=1)[0]
    return f"{clean(first_artist)}|{clean(title)}"


# ---------------------------------------------------------------------------
# Reading files
# ---------------------------------------------------------------------------

def _read_table(name: str, data: bytes) -> object:
    """Return a DataFrame for tabular files, or the parsed JSON (a list or a dict)."""
    if name.lower().endswith(".json") or data.lstrip()[:1] in (b"[", b"{"):
        return json.loads(data.decode("utf-8-sig"))
    # The Music app writes UTF-16 tab-separated text
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return pd.read_csv(io.StringIO(data.decode("utf-16")), sep="\t")
    text = data.decode("utf-8-sig", errors="replace")
    sep = "\t" if text.split("\n", 1)[0].count("\t") > text.split("\n", 1)[0].count(",") else ","
    return pd.read_csv(io.StringIO(text), sep=sep)


def _aggregate_plays(rows: Iterable[tuple], source: str) -> pd.DataFrame:
    """rows: (title, artist, album, ms_played, explicitly_skipped[, when, uri]).

    `when` is the play's timestamp as text ("2021-03-04T22:10:05Z" or "2021-03-04 22:10");
    the first ten characters (the date) give first_played / last_played."""
    agg: Dict[str, dict] = {}
    for title, artist, album, ms, skipped, *extra in rows:
        if not title or not artist:
            continue
        when = str(extra[0])[:10] if extra and extra[0] else None
        uri = extra[1] if len(extra) > 1 else None
        k = song_key(artist, title)
        a = agg.get(k)
        if a is None:
            a = agg[k] = {"title": title, "artist": artist, "album": album or None,
                          "play_count": 0, "skip_count": 0, "minutes_played": 0.0,
                          "first_played": when, "last_played": when, "uri": uri}
        ms = float(ms or 0)
        if skipped or ms < SKIP_MS:
            a["skip_count"] += 1
        else:
            a["play_count"] += 1
        a["minutes_played"] += ms / 60000
        if when:
            if not a["first_played"] or when < a["first_played"]:
                a["first_played"] = when
            if not a["last_played"] or when > a["last_played"]:
                a["last_played"] = when
        if uri and not a["uri"]:
            a["uri"] = uri
    df = pd.DataFrame(agg.values())
    if len(df):
        df["minutes_played"] = df["minutes_played"].round(1)
        df["source"] = source
    return df


def parse_file(name: str, data: bytes) -> Tuple[pd.DataFrame, str]:
    """Parse one export. Returns (canonical rows, a label for what it was)."""
    raw = _read_table(name, data)

    # ---- Spotify account data: YourLibrary.json and Playlist*.json ---------------
    if isinstance(raw, dict):
        if isinstance(raw.get("playlists"), list):
            return _spotify_playlists(raw["playlists"]), "Spotify playlists (account data)"
        if isinstance(raw.get("tracks"), list) and ({"albums", "artists", "shows", "bannedTracks"} & set(raw)):
            df = _canonical_from_columns(pd.DataFrame([t for t in raw["tracks"] if isinstance(t, dict)]), "spotify_library")
            if len(df):
                df["liked"] = True
            return df, "Spotify liked songs (YourLibrary.json)"
        raw = raw.get("tracks", raw.get("items", [raw]))

    # ---- JSON exports --------------------------------------------------------
    if isinstance(raw, list):
        recs = [r for r in raw if isinstance(r, dict)]
        keys = {_norm(k) for r in recs[:20] for k in r}
        if "master_metadata_track_name" in keys or "episode_name" in keys:  # Spotify extended history
            # Podcast episodes have no track name and are skipped by _aggregate_plays
            rows = ((r.get("master_metadata_track_name"), r.get("master_metadata_album_artist_name"),
                     r.get("master_metadata_album_album_name"), r.get("ms_played"), bool(r.get("skipped")),
                     r.get("ts"), r.get("spotify_track_uri"))
                    for r in recs)
            return _aggregate_plays(rows, "spotify_history"), "Spotify extended streaming history"
        if "trackname" in keys and "msplayed" in keys:  # Spotify basic history
            rows = ((r.get("trackName"), r.get("artistName"), None, r.get("msPlayed"), False, r.get("endTime"))
                    for r in recs)
            return _aggregate_plays(rows, "spotify_history"), "Spotify streaming history"
        if "podcastname" in keys or "episodename" in keys:
            return pd.DataFrame(), "Spotify podcast history (skipped: no songs in it)"
        # Apple Music Library Tracks.json and other track lists
        df = pd.DataFrame(recs)
        label = "Apple Music library" if "play_count" in {_norm(c) for c in df.columns} else "track list (JSON)"
        return _canonical_from_columns(df, "apple_library" if label.startswith("Apple") else "json"), label

    df = raw.copy()
    df.columns = [_norm(c) for c in df.columns]
    cols = set(df.columns)

    # ---- Apple Music play activity (one row per play event) --------------------
    if "play_duration_milliseconds" in cols and _first(df, "song_name", "content_name") and "play_count" not in cols:
        t, a = _first(df, "song_name", "content_name"), _first(df, "artist_name", "container_artist_name")
        al = _first(df, "album_name", "container_album_name")
        reason = df["end_reason_type"].astype(str).str.upper() if "end_reason_type" in cols else pd.Series([""] * len(df))
        when = _first(df, "event_start_timestamp", "event_timestamp", "play_date_utc")
        none = [None] * len(df)
        # Plain columns rather than iterrows: Apple's file is often 100,000+ rows wide with ~100 columns
        rows = zip(df[t].tolist(), df[a].tolist() if a else none, df[al].tolist() if al else none,
                   df["play_duration_milliseconds"].tolist(), ("SKIP" in r for r in reason.tolist()),
                   df[when].tolist() if when else none)
        return _aggregate_plays(rows, "apple_history"), "Apple Music play activity"

    # ---- Apple Music daily / track play history (already counted) --------------
    if "track_description" in cols and "play_count" in cols:
        parts = df["track_description"].astype(str).str.split(" - ", n=1, expand=True)
        out = pd.DataFrame({
            "artist": parts[0].str.strip(),
            "title": (parts[1] if parts.shape[1] > 1 else parts[0]).astype(str).str.strip(),
            "play_count": pd.to_numeric(df["play_count"], errors="coerce").fillna(0),
            "skip_count": pd.to_numeric(df.get("skip_count", 0), errors="coerce").fillna(0),
        })
        if "play_duration_milliseconds" in cols:
            out["minutes_played"] = pd.to_numeric(df["play_duration_milliseconds"], errors="coerce").fillna(0) / 60000
        out = out.groupby(out.apply(lambda r: song_key(r["artist"], r["title"]), axis=1)).agg(
            {"artist": "first", "title": "first", "play_count": "sum", "skip_count": "sum",
             **({"minutes_played": "sum"} if "minutes_played" in out else {})}).reset_index(drop=True)
        out["source"] = "apple_history"
        return out, "Apple Music play history"

    # ---- Exportify (Spotify playlists) -------------------------------------------
    if "track_name" in cols and _first(df, "artist_names", "artist_name"):
        return _canonical_from_columns(df, "spotify_playlist"), "Spotify playlist (Exportify)"

    # ---- Music app playlist export (.txt) ------------------------------------------
    if {"name", "artist"} <= cols and ("plays" in cols or "time" in cols):
        return _canonical_from_columns(df, "apple_playlist"), "Apple Music playlist export"

    return _canonical_from_columns(df, "csv"), "track list (CSV)"


def _spotify_playlists(playlists: List[dict]) -> pd.DataFrame:
    """Playlist*.json: one row per song, with the names of the playlists it is in."""
    agg: Dict[str, dict] = {}
    for pl in playlists:
        name = str(pl.get("name") or "Untitled playlist")
        for item in pl.get("items") or []:
            t = (item or {}).get("track") or {}
            title, artist = t.get("trackName"), t.get("artistName")
            if not title or not artist:
                continue
            k = song_key(artist, title)
            a = agg.setdefault(k, {"title": title, "artist": artist, "album": t.get("albumName"),
                                   "uri": t.get("trackUri"), "playlists": [], "added_at": None})
            if name not in a["playlists"]:
                a["playlists"].append(name)
            added = str(item.get("addedDate") or "")[:10] or None
            if added and (not a["added_at"] or added < a["added_at"]):
                a["added_at"] = added
    df = pd.DataFrame(agg.values())
    if len(df):
        df["playlists"] = df["playlists"].map("; ".join)
        df["source"] = "spotify_playlists"
    return df


def _canonical_from_columns(df: pd.DataFrame, source: str) -> pd.DataFrame:
    df = df.copy()
    df.columns = [_norm(c) for c in df.columns]
    pick = lambda *n: _first(df, *n)  # noqa: E731
    out = pd.DataFrame(index=df.index)
    mapping = {
        "title": pick("title", "track_name", "name", "song", "song_name", "track"),
        "artist": pick("artist", "artist_names", "artist_name", "artists", "album_artist"),
        "album": pick("album", "album_name"),
        "genre": pick("genre", "genres", "artist_genres", "album_genres", "tags"),
        "key": pick("key", "musical_key", "camelot"),
        "mode": pick("mode"),
        "bpm": pick("bpm", "tempo", "beats_per_minute"),
        "year": pick("year", "release_year", "track_year", "album_release_date", "release_date"),
        "play_count": pick("play_count", "plays", "playcount", "listens", "streams"),
        "skip_count": pick("skip_count", "skips"),
        "liked": pick("liked", "loved", "favorite", "favourite", "is_liked"),
        "rating": pick("rating", "my_rating", "stars"),
        "minutes_played": pick("minutes_played"),
        "first_played": pick("first_played"),
        "last_played": pick("last_played"),
        "playlists": pick("playlists", "playlist", "playlist_name"),
        "added_at": pick("added_at", "date_added", "added"),
        "uri": pick("uri", "track_uri", "spotify_uri", "spotify_track_uri"),
    }
    for dst, src in mapping.items():
        if src:
            out[dst] = df[src]
    for f in ["energy", "danceability", "valence", "acousticness", "instrumentalness", "speechiness", "liveness",
              "loudness", "brightness"]:
        if f in df.columns:
            out[f] = df[f]
    if "year" in out:
        out["year"] = pd.to_numeric(out["year"].astype(str).str[:4], errors="coerce")
    if "artist" in out:  # Exportify joins artists with commas; keep the first for matching
        out["artist"] = out["artist"].astype(str).str.split(",").str[0].str.strip()
    out["source"] = source
    return out.reset_index(drop=True)


def _truthy(v) -> bool:
    return str(v).strip().lower() in {"1", "1.0", "true", "yes", "y", "♥", "x"}


def merge(frames: List[pd.DataFrame]) -> pd.DataFrame:
    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        raise ValueError("None of the files had any songs in them.")
    df = pd.concat(frames, ignore_index=True, sort=False)
    for c in CANONICAL:
        if c not in df:
            df[c] = np.nan
    df = df[df["title"].notna() & (df["title"].astype(str).str.strip() != "")]
    df["_k"] = [song_key(a, t) for a, t in zip(df["artist"], df["title"])]
    sums = ["play_count", "skip_count", "minutes_played"]
    for c in sums:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["first_played", "last_played", "added_at"]:  # ISO dates: text order is time order
        df[c] = df[c].map(lambda v: None if v is None or (isinstance(v, float) and np.isnan(v)) or v == "" else str(v)[:10])
    agg = {c: "first" for c in CANONICAL if c not in sums and c != "source"}
    agg.update({c: "sum" for c in sums})
    # Not "min"/"max": pandas 2 can't compare None with text in those
    earliest = lambda s: min(s.dropna(), default=None)  # noqa: E731
    agg.update(first_played=earliest, last_played=lambda s: max(s.dropna(), default=None), added_at=earliest)
    agg["source"] = lambda s: "+".join(sorted(set(map(str, s.dropna()))))
    agg["playlists"] = lambda s: "; ".join(dict.fromkeys(p.strip() for v in s.dropna() for p in str(v).split(";")
                                                         if p.strip())) or None
    agg["liked"] = lambda s: True if s.map(_truthy).any() else (s.dropna().iloc[0] if s.notna().any() else None)
    merged = df.groupby("_k", sort=False).agg(agg).reset_index(drop=True)
    for c in sums:
        if df[c].notna().sum() == 0:
            merged[c] = np.nan  # nobody had listening data; don't fake zeros
    return merged[CANONICAL]


# ---------------------------------------------------------------------------
# Online enrichment: Deezer metadata + local analysis of the 30 s preview
# ---------------------------------------------------------------------------

def _cache_dir() -> Path:
    # v2: older entries could belong to a different artist's song with a similar title
    d = settings.DATA_DIR / "cache" / "deezer_v2"
    d.mkdir(parents=True, exist_ok=True)
    return d


_deezer = genres.Throttle(0.12)  # Deezer allows 50 requests every 5 s; stay a bit under 10 a second
_albums: Dict[int, dict] = {}  # songs on one album share its genre and release date


def _get(url: str) -> dict:
    if "api.deezer.com" in url:
        _deezer.wait()
    req = urllib.request.Request(url, headers={"User-Agent": "SuperMusic/0.1"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def estimate_key(y: np.ndarray, sr: int) -> Optional[str]:
    """Krumhansl-Schmuckler: correlate the average chroma with major/minor key profiles."""
    import librosa

    chroma = librosa.feature.chroma_stft(y=y, sr=sr).mean(axis=1)
    if not np.any(chroma):
        return None
    best, name = -2.0, None
    for tonic in range(12):
        for profile, suffix in ((_MAJOR, ""), (_MINOR, "m")):
            r = np.corrcoef(chroma, np.roll(profile, tonic))[0, 1]
            if r > best:
                best, name = r, _NAMES[tonic] + suffix
    return name


def analyse_preview(mp3: bytes) -> dict:
    import tempfile

    import librosa

    # libsndfile in the image can't decode MP3 from memory; a temp file lets librosa fall back to ffmpeg
    with tempfile.NamedTemporaryFile(suffix=".mp3") as f:
        f.write(mp3)
        f.flush()
        y, sr = librosa.load(f.name, sr=22050, mono=True)
    return analyse_audio(y, sr)


def analyse_audio(y: np.ndarray, sr: int) -> dict:
    """Tempo, key, energy and brightness from mono audio (the map's audio-derived features)."""
    import librosa

    if len(y) < sr * 5:
        return {}
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    rms = float(np.sqrt(np.mean(y**2)))
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    key = estimate_key(y, sr)
    return {
        "bpm": round(float(np.atleast_1d(tempo)[0]), 1),
        "key": key,
        # 0..1 scales so they sit alongside Spotify-style features
        "energy": round(float(np.clip((20 * np.log10(rms + 1e-9) + 35) / 30, 0, 1)), 3),
        "brightness": round(float(np.clip(centroid / 5000, 0, 1)), 3),
    }


def _title_matches(want: str, got: str) -> bool:
    a, b = song_key("", want).split("|")[1], song_key("", got).split("|")[1]
    return bool(a) and bool(b) and (a == b or a.startswith(b) or b.startswith(a))


def _pick_hit(hits: List[dict], artist: str, title: str) -> Optional[dict]:
    """The search hit for this song by this artist, or None.

    Deezer's search happily returns a different artist's song with a
    similar title; taking it anyway gave songs someone else's genre."""
    by_artist = [h for h in hits if genres.same_artist(h.get("artist", {}).get("name", ""), artist)]
    return next((h for h in by_artist if _title_matches(title, h.get("title", ""))), None) or \
        next((h for h in by_artist if _title_matches(title, h.get("title_short", ""))), None)


def lookup(artist: str, title: str, analyse: bool = True) -> dict:
    """Genre, year (and preview features) for one song, cached on disk."""
    cache = _song_cache(artist, title)
    fresh = False
    if cache.exists():
        info = json.loads(cache.read_text())
    else:
        info = {}
        try:
            q = urllib.parse.quote(f'artist:"{artist}" track:"{title}"')
            hits = _get(f"https://api.deezer.com/search?q={q}&limit=10").get("data", [])
            hit = _pick_hit(hits, artist, title)
            if not hit:  # the strict query misses some spellings; try a loose one
                q = urllib.parse.quote(f"{artist} {title}")
                hit = _pick_hit(_get(f"https://api.deezer.com/search?q={q}&limit=10").get("data", []), artist, title)
            if hit:
                info["deezer_id"] = hit["id"]
                album = _album(hit["album"]["id"])
                info["deezer_genres"] = [g["name"] for g in album.get("genres", {}).get("data", [])]
                if album.get("release_date"):
                    info["year"] = int(album["release_date"][:4])
                track = _get(f"https://api.deezer.com/track/{hit['id']}")
                if track.get("bpm"):
                    info["bpm"] = track["bpm"]
                if analyse and hit.get("preview"):
                    try:
                        with urllib.request.urlopen(hit["preview"], timeout=20) as r:
                            feats = analyse_preview(r.read())
                        info = {**feats, **info}  # Deezer's own BPM wins when it has one
                    except Exception as e:
                        info["preview_error"] = str(e)[:120]
        except Exception as e:  # network trouble shouldn't kill the import
            info["error"] = str(e)[:120]
        if "error" not in info:
            cache.write_text(json.dumps(info))
            fresh = True
    # Genre comes from listener tags (Last.fm / MusicBrainz) first, Deezer's album genre last.
    # Older cache files stored Deezer's raw genre as "genre"; it is ignored now.
    info = {k: v for k, v in info.items() if k != "genre"}
    found, source = genres.lookup_genres(artist, title, info.get("deezer_genres"))
    if found:
        info["genre"] = ";".join(found)
        info["genre_source"] = source
    from app.core import community  # shared with everyone's imports (imported here: it imports us)
    community.record_lookup(artist, title, info, only_if_new=not fresh)
    return info


def _album(album_id: int) -> dict:
    if album_id not in _albums:
        a = _get(f"https://api.deezer.com/album/{album_id}")
        _albums[album_id] = {"genres": a.get("genres", {}), "release_date": a.get("release_date")}
    return _albums[album_id]


def _song_cache(artist: str, title: str) -> Path:
    return _cache_dir() / (re.sub(r"[^a-z0-9|]+", "_", song_key(artist, title))[:150] + ".json")


def is_cached(artist: str, title: str) -> bool:
    """True if looking this song up needs no network request (it was looked up before)."""
    return _song_cache(artist, title).exists() and genres.is_cached(artist)


def enrich(df: pd.DataFrame, limit: int = 1500, analyse: bool = True,
           progress: Optional[Callable[[int, int], None]] = None,
           on_song: Optional[Callable[[dict], None]] = None,
           on_start: Optional[Callable[[dict], None]] = None,
           give_up_after: int = 8, workers: int = 8) -> Tuple[pd.DataFrame, int]:
    """Fill missing genre/year/bpm/key/energy for up to `limit` songs, most-played first.

    `on_start` gets {"needed", "todo", "cached"} before the first lookup: songs missing
    something, songs that will be looked up (at most `limit`), and how many of those were
    looked up before. `on_song` gets one dict per song: {"cached", "found", "error", "seconds"},
    where "seconds" is the time since the previous song finished (so with several lookups
    running at once it measures throughput, which is what the time-left estimate needs).
    Songs are looked up one at a time until one works, then `workers` at a time; each
    online service has its own rate limit (genres.Throttle), so going wider never floods
    them. If the first `give_up_after` lookups all fail with network errors, the rest are
    skipped (the services can't be reached) and `on_song` gets {"gave_up": True}."""
    df = df.copy()
    for f in ["genre", "key"]:  # all-empty columns are float; let them hold text
        df[f] = df[f].astype(object)
    order = df["play_count"].fillna(0).sort_values(ascending=False).index if df["play_count"].notna().any() else df.index
    needed = [i for i in order if pd.isna(df.at[i, "genre"]) or pd.isna(df.at[i, "bpm"])]
    todo = needed[:limit]
    if on_start:
        on_start({"needed": len(needed), "todo": len(todo),
                  "cached": sum(is_cached(str(df.at[i, "artist"] or ""), str(df.at[i, "title"])) for i in todo)})

    # Read names up front: worker threads never touch df while results are written to it
    names = {i: (str(df.at[i, "artist"] or ""), str(df.at[i, "title"])) for i in todo}

    def one(i):
        artist, title = names[i]
        cached = is_cached(artist, title)
        return i, cached, lookup(artist, title, analyse=analyse)

    found = errors = successes = done = 0
    last = time.monotonic()

    def record(i, cached, info) -> None:
        nonlocal found, errors, successes, done, last
        hit = bool(info.get("deezer_id") or info.get("genre"))
        found += hit
        failed = "error" in info and not hit
        errors += failed
        successes += not failed
        done += 1
        for f in ["genre", "year", "bpm", "key", "energy", "brightness"]:
            if f in info and pd.isna(df.at[i, f]):
                df.at[i, f] = info[f]
        now = time.monotonic()
        if on_song:
            on_song({"cached": cached, "found": hit, "error": failed, "seconds": now - last})
        last = now
        if progress:
            progress(done, len(todo))

    # One at a time until something works, so an offline machine gives up after a few tries
    for i in todo:
        record(*one(i))
        if successes:
            break
        if errors >= give_up_after:
            if on_song:
                on_song({"gave_up": True, "skipped": len(todo) - done})
            return df, found
    rest = todo[done:]
    if rest:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            for fut in as_completed([pool.submit(one, i) for i in rest]):
                record(*fut.result())  # results are written to df here, on this thread only
    return df, found
