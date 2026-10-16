"""
Import a listener's library straight from Last.fm, by username.

Last.fm's API is open: anyone's public listening data can be read with one free
API key (LASTFM_API_KEY), with no sign-in and no cap on how many people use it.
That makes it the easiest "one click" way into the Music Map, unlike Spotify,
whose API only lets 5 hand-picked users in until an app is approved.

What is read (all public, no password needed):

  * user.getTopTracks   every song you've scrobbled, with its all-time play count
                        (most-played first, up to `max_tracks`)
  * user.getLovedTracks songs you've hearted, which become `liked`
  * user.getRecentTracks your latest scrobbles (up to `recent_pages` x 200), which
                        give last-played dates and which songs you play back to
                        back (the map's "played together" hidden links)

The result has the same columns as any other import (library_import.CANONICAL),
so it is merged and enriched the same way. Genres come from Last.fm's own tags
during enrichment (genres.py uses Last.fm first when the key is set).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

from app.core import genres, library_import

API = "https://ws.audioscrobbler.com/2.0/"
TOP_PAGE = 1000    # the most Last.fm returns per page for top and loved tracks
RECENT_PAGE = 200  # ... and for recent tracks
MAX_LOVED_PAGES = 10


class LastfmError(Exception):
    """A problem worth showing the listener as it is (unknown user, no key, private profile)."""


def api_key() -> str:
    return os.getenv("LASTFM_API_KEY", "").strip()


def enabled() -> bool:
    return bool(api_key())


def _call(method: str, **params) -> dict:
    key = api_key()
    if not key:
        raise LastfmError("Last.fm import needs a free LASTFM_API_KEY in the server's .env "
                          "(get one at https://www.last.fm/api/account/create).")
    q = {"method": method, "api_key": key, "format": "json", **{k: v for k, v in params.items() if v is not None}}
    url = API + "?" + urllib.parse.urlencode(q)
    try:
        data = genres._get(url, timeout=30)  # shares genres.py's Last.fm rate limit
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read())
        except Exception:
            raise LastfmError(f"Last.fm didn't answer ({e.code}). Try again in a minute.") from e
    if isinstance(data, dict) and data.get("error"):
        code, msg = data.get("error"), data.get("message") or "Last.fm error"
        if code == 6:
            raise LastfmError(f"There's no Last.fm user called \"{params.get('user')}\". Check the spelling.")
        if code == 17:
            raise LastfmError("That Last.fm profile hides its listening history. "
                              "Turn off \"Hide recent listening\" in Last.fm's privacy settings, then try again.")
        if code in (10, 26):
            raise LastfmError("The server's LASTFM_API_KEY isn't valid. Check it in .env.")
        if code == 29:
            raise LastfmError("Last.fm says we're asking too fast. Try again in a minute.")
        raise LastfmError(f"Last.fm said: {msg}")
    return data


def _list(block: dict, name: str) -> Tuple[List[dict], int]:
    """(items, total pages) from a paged Last.fm answer."""
    items = (block or {}).get(name) or []
    if isinstance(items, dict):  # a single item comes back as an object, not a list
        items = [items]
    pages = int(((block or {}).get("@attr") or {}).get("totalPages") or 1)
    return items, pages


def _artist(t: dict) -> str:
    a = t.get("artist") or {}
    return str(a.get("name") or a.get("#text") or "").strip() if isinstance(a, dict) else str(a).strip()


def _date(uts) -> Optional[str]:
    try:
        return datetime.fromtimestamp(int(uts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None


def user_info(username: str) -> dict:
    u = _call("user.getinfo", user=username).get("user") or {}
    return {
        "name": u.get("name") or username,
        "playcount": int(u.get("playcount") or 0),
        "tracks": int(u.get("track_count") or 0) or None,
        "registered": _date((u.get("registered") or {}).get("unixtime")),
        "url": u.get("url"),
    }


def _pages(method: str, name: str, first: dict, pages: int, workers: int = 4, **params) -> List[dict]:
    """Fetch pages 2..pages of a list in parallel (each still waits its turn for the rate limit)."""
    items, _ = _list(first, name)
    if pages < 2:
        return items

    def one(p: int) -> List[dict]:
        block = _call(method, page=p, **params).get(method.split(".get")[1].lower(), {})
        return _list(block, name)[0]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for got in pool.map(one, range(2, pages + 1)):
            items.extend(got)
    return items


def fetch(username: str, max_tracks: int = 2000, recent_pages: int = 25,
          progress: Optional[Callable[[str, float], None]] = None) -> Tuple[pd.DataFrame, dict]:
    """A listener's Last.fm library as canonical rows, plus a summary of what was read.

    progress(message, fraction) is called as each part arrives (fraction 0..1)."""
    username = str(username or "").strip()
    if not username:
        raise LastfmError("Type your Last.fm username first.")
    say = progress or (lambda msg, frac: None)
    say(f"Finding {username} on Last.fm…", 0.0)
    info = user_info(username)
    user = info["name"]

    # Top tracks: every scrobbled song with its all-time play count
    say(f"Reading {user}'s top tracks…", 0.1)
    per = min(TOP_PAGE, max(1, max_tracks))
    first = _call("user.gettoptracks", user=user, period="overall", limit=per, page=1).get("toptracks", {})
    _, total_pages = _list(first, "track")
    want_pages = min(total_pages, -(-max_tracks // per))
    top = _pages("user.gettoptracks", "track", first, want_pages, user=user, period="overall", limit=per)[:max_tracks]
    rows: List[dict] = []
    for t in top:
        title, artist = str(t.get("name") or "").strip(), _artist(t)
        if title and artist:
            rows.append({"title": title, "artist": artist, "play_count": int(t.get("playcount") or 0),
                         "uri": t.get("url"), "source": "Last.fm"})
    top_df = pd.DataFrame(rows)
    top_keys = {library_import.song_key(r["artist"], r["title"]) for r in rows}

    # Loved tracks become liked
    say(f"Reading {user}'s loved tracks…", 0.45)
    first = _call("user.getlovedtracks", user=user, limit=TOP_PAGE, page=1).get("lovedtracks", {})
    _, loved_pages = _list(first, "track")
    loved = _pages("user.getlovedtracks", "track", first, min(loved_pages, MAX_LOVED_PAGES), user=user, limit=TOP_PAGE)
    loved_df = pd.DataFrame([
        {"title": str(t.get("name") or "").strip(), "artist": _artist(t), "liked": True,
         "added_at": _date((t.get("date") or {}).get("uts")), "uri": t.get("url"), "source": "Last.fm"}
        for t in loved if t.get("name") and _artist(t)
    ])

    # Recent scrobbles: last-played dates, albums and back-to-back plays
    recent_df = pd.DataFrame()
    scrobbles = 0
    whole_history = False
    if recent_pages > 0:
        say(f"Reading {user}'s recent scrobbles…", 0.6)
        first = _call("user.getrecenttracks", user=user, limit=RECENT_PAGE, page=1).get("recenttracks", {})
        _, r_pages = _list(first, "track")
        whole_history = r_pages <= recent_pages
        recent = _pages("user.getrecenttracks", "track", first, min(r_pages, recent_pages), user=user, limit=RECENT_PAGE)
        plays = []
        for t in recent:
            if (t.get("@attr") or {}).get("nowplaying"):
                continue  # playing right now: not a finished scrobble yet
            when = _date((t.get("date") or {}).get("uts"))
            album = (t.get("album") or {}).get("#text") or None
            # A scrobble means the song was played for at least half its length, so it counts as a play
            plays.append((t.get("name"), _artist(t), album, library_import.SKIP_MS, False, when))
        scrobbles = len(plays)
        recent_df = library_import._aggregate_plays(plays, "Last.fm")
        if len(recent_df):
            keys = [library_import.song_key(a, t) for a, t in zip(recent_df["artist"], recent_df["title"])]
            in_top = pd.Series([k in top_keys for k in keys], index=recent_df.index)
            # Top tracks already hold the all-time count; don't add the recent plays on top of it
            for c in ["play_count", "skip_count", "minutes_played"]:
                recent_df[c] = recent_df[c].where(~in_top)
            recent_df["skip_count"] = None
            recent_df["minutes_played"] = None
            if not whole_history:
                recent_df["first_played"] = None  # only the oldest scrobble we read, not the real first play

    say("Combining…", 0.95)
    if not (len(top_df) or len(loved_df) or len(recent_df)):
        raise LastfmError(f"{user} hasn't scrobbled any songs yet, so there's nothing to import.")
    df = library_import.merge([top_df, loved_df, recent_df])
    summary = {
        "user": user,
        "url": info.get("url"),
        "scrobbles_total": info["playcount"],
        "registered": info["registered"],
        "top_tracks": int(len(top_df)),
        "loved": int(len(loved_df)),
        "recent_scrobbles": scrobbles,
        "whole_history": whole_history,
    }
    return df, summary
