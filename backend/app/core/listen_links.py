"""Finding songs to play: 30-second Deezer previews for Map Radio, and YouTube video ids
for turning a station into a YouTube playlist.

Deezer's API needs no key and every song has a 30 s preview, which is what the importer
already analyses. Its API sends no CORS headers, so the browser asks us and we ask Deezer.
Preview links expire after a while, so a fresh one is fetched each time; only the Deezer
track id is cached.

YouTube's official API allows ~100 searches a day per app, far too few, so video ids are
found with yt-dlp's search (no key, no quota) and cached on disk.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional

from app.core import library_import
from app.core.config import settings

_lock = threading.Lock()


def _cache_file(name: str) -> Path:
    d = settings.DATA_DIR / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def _load(name: str) -> Dict[str, Optional[str]]:
    f = _cache_file(name)
    try:
        return json.loads(f.read_text()) if f.exists() else {}
    except Exception:
        return {}


def _save(name: str, key: str, value) -> None:
    with _lock:
        data = _load(name)
        data[key] = value
        _cache_file(name).write_text(json.dumps(data))


def _deezer_id(artist: str, title: str) -> Optional[int]:
    key = library_import.song_key(artist, title)
    known = _load("deezer_ids.json")
    if key in known:
        return known[key]
    # A song the importer already looked up has its id in the importer's cache
    song_cache = library_import._song_cache(artist, title)
    if song_cache.exists():
        try:
            found = json.loads(song_cache.read_text()).get("deezer_id")
            if found:
                return found
        except Exception:
            pass
    found = None
    for q in (f'artist:"{artist}" track:"{title}"', f"{artist} {title}"):
        hits = library_import._get(f"https://api.deezer.com/search?q={urllib.parse.quote(q)}&limit=10").get("data", [])
        hit = library_import._pick_hit(hits, artist, title) if artist else (hits[0] if hits else None)
        if hit:
            found = hit["id"]
            break
    _save("deezer_ids.json", key, found)
    return found


def preview(artist: str, title: str) -> Dict[str, Optional[str]]:
    """{"preview": mp3 url or None, "deezer_url": the song's Deezer page}."""
    track_id = _deezer_id(artist or "", title)
    if not track_id:
        return {"preview": None, "deezer_url": None}
    track = library_import._get(f"https://api.deezer.com/track/{track_id}")
    return {"preview": track.get("preview") or None, "deezer_url": track.get("link"),
            "cover": (track.get("album") or {}).get("cover_medium")}


def _yt_search(query: str) -> Optional[str]:
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        raise RuntimeError("yt-dlp isn't installed on the server (pip install yt-dlp).")
    proc = subprocess.run([ytdlp, "--flat-playlist", "--print", "id", "--no-warnings", f"ytsearch1:{query}"],
                          capture_output=True, text=True, timeout=40)
    vid = proc.stdout.strip().splitlines()[0].strip() if proc.stdout.strip() else ""
    return vid if len(vid) == 11 else None


def youtube_id_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    u = urllib.parse.urlparse(url)
    if u.hostname == "youtu.be":
        vid = u.path.lstrip("/")[:11]
    else:
        vid = (urllib.parse.parse_qs(u.query).get("v") or [""])[0]
    return vid if len(vid) == 11 else None


def youtube_ids(songs: List[dict]) -> List[Optional[str]]:
    """One video id (or None) per {artist, title, youtube_url?}, in order."""
    known = _load("youtube_ids.json")

    def one(s: dict) -> Optional[str]:
        direct = youtube_id_from_url(s.get("youtube_url"))
        if direct:
            return direct
        query = " - ".join(x for x in (s.get("artist"), s.get("title")) if x)
        key = library_import.song_key(s.get("artist") or "", s.get("title") or "")
        if key in known:
            return known[key]
        try:
            vid = _yt_search(query)
        except subprocess.TimeoutExpired:
            return None
        if vid:  # a miss may be a hiccup; try again next time
            _save("youtube_ids.json", key, vid)
        return vid

    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(one, songs))
