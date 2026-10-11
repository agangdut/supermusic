"""
Look up a song's genre online and boil the answer down to a short, plain list.

Online sources disagree and use very different words ("Rap/Hip Hop",
"conscious hip hop", "seen live", "british"), so every tag is mapped onto
one small vocabulary (Pop, Hip-Hop, R&B, Rock, Electronic, ...) and tags
that aren't genres are dropped. A song gets at most two genres, strongest
first.

Sources, best first (the first one that knows the artist wins):

  1. Last.fm track and artist tags, only if LASTFM_API_KEY is set. Tags are
     voted on by listeners, so they are the most accurate.
  2. MusicBrainz artist tags. Free, no key; at most one request a second.
  3. Deezer's album genre, only for a search hit by the same artist. Deezer
     files whole albums under one coarse genre and leans heavily on
     "Rap/Hip Hop", which is why it is the last resort.

Results are cached per artist (and per song for Last.fm) under
data/cache/genres, so each artist is only looked up once.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from app.core.config import settings

MAX_GENRES = 2
UA = "SuperMusic/0.2 (https://github.com/agangdut/supermusic)"

# Ordered: the first rule that matches a tag decides its genre, so specific
# rules ("pop rap", "neo soul", "synthpop") come before broad ones ("pop").
_RULES: List[Tuple[str, str]] = [
    ("K-Pop", r"\bk[- ]?pop\b|korean pop"),
    ("Latin", r"latin|reggaet|salsa|bachata|cumbia|bossa|samba|\bmpb\b|sertanejo|\bbanda\b|corrido|mexican|"
              r"brazil|tango|dembow|urbano|flamenco|merengue"),
    ("Afrobeats", r"afro|amapiano|naija|highlife|african"),
    ("Gospel", r"gospel|christian|worship|\bccm\b"),
    ("R&B", r"r&b|\br ?n ?b\b|r'n'b|rhythm and blues|neo[- ]?soul|quiet storm"),
    ("Hip-Hop", r"hip[- ]?hop|\brap\b|\brapper|\btrap\b|\bdrill\b|\bgrime\b|boom bap|gangsta|crunk|phonk"),
    ("Metal", r"metal|djent"),
    ("Punk", r"punk|\bemo\b|hardcore|screamo"),
    ("Soundtrack", r"soundtrack|\bscore\b|\bfilms?\b|\bgames?\b|musical|show ?tunes|\banime\b"),
    ("Classical", r"classical|orchestr|opera|symphon|chamber music|baroque|romantic era|contemporary classical"),
    ("Rock", r"rock|grunge|shoegaze|britpop|new wave"),
    # "dance pop", "synthpop", "indie pop", "art pop": pop is the head word
    ("Pop", r"pop$"),
    ("Jazz", r"jazz|swing|bebop|big band"),
    ("Blues", r"blues"),
    ("Country", r"country|bluegrass|honky"),
    ("Folk", r"folk|singer[- ]songwriter|americana|acoustic"),
    ("Reggae", r"reggae|dancehall|\bska\b|\bdub\b"),
    ("Soul", r"soul|motown"),
    ("Funk", r"funk|disco|boogie"),
    ("Electronic", r"electr|\bedm\b|house|techno|trance|dubstep|drum (and|n|&) bass|\bdnb\b|jungle|garage|synthwave|"
                   r"ambient|\bidm\b|downtempo|\bdance\b|future bass|breakbeat|trip[- ]?hop|chillwave|hardstyle|"
                   r"lo-?fi|chillout|\bchill\b"),
    ("Alternative", r"indie|alternative|\balt\b"),
    ("Pop", r"\bpop\b"),
    ("World", r"world|celtic|bollywood|indian|desi|filmi|asian music|j-?rock"),
]
_COMPILED = [(g, re.compile(rx)) for g, rx in _RULES]
GENRES = sorted({g for g, _ in _RULES})


def canonical(tag: str) -> Optional[str]:
    """One tag ("conscious hip hop", "Rap/Hip Hop", "seen live") -> one genre, or None if it isn't one."""
    t = re.sub(r"\s+", " ", str(tag).strip().lower().replace("_", " "))
    if not t:
        return None
    for genre, rx in _COMPILED:
        if rx.search(t):
            return genre
    return None


def summarise(tags: Iterable[Tuple[str, float]], max_genres: int = MAX_GENRES) -> List[str]:
    """Weighted tags -> up to `max_genres` genres, strongest first.

    A second genre is kept only if it has at least 40% of the top one's
    weight, so a single stray tag can't relabel an artist."""
    score: Dict[str, float] = {}
    for name, weight in tags:
        g = canonical(name)
        if g and weight > 0:
            score[g] = score.get(g, 0.0) + float(weight)
    if not score:
        return []
    ranked = sorted(score.items(), key=lambda kv: -kv[1])
    top = ranked[0][1]
    return [g for g, s in ranked[:max_genres] if s >= 0.4 * top]


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------

def _get(url: str, timeout: float = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


_mb_lock = threading.Lock()
_mb_last = [0.0]


def _mb_get(url: str) -> dict:
    """MusicBrainz allows one request a second per client."""
    with _mb_lock:
        wait = 1.05 - (time.monotonic() - _mb_last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            return _get(url)
        finally:
            _mb_last[0] = time.monotonic()


def _clean(s: str) -> str:
    s = str(s or "").lower()
    s = re.sub(r"^the\s+", "", s)
    s = s.replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "", s)


def _first_artist(artist: str) -> str:
    return re.split(r",|;| & | feat\.? | ft\.? | x | with ", str(artist or ""), maxsplit=1)[0].strip()


def same_artist(a: str, b: str) -> bool:
    ca, cb = _clean(_first_artist(a)), _clean(_first_artist(b))
    return bool(ca) and ca == cb


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def lastfm_tags(artist: str, title: Optional[str] = None) -> List[Tuple[str, float]]:
    key = os.getenv("LASTFM_API_KEY", "").strip()
    if not key:
        return []
    base = "https://ws.audioscrobbler.com/2.0/?format=json&autocorrect=1&api_key=" + urllib.parse.quote(key)
    a = "&artist=" + urllib.parse.quote(_first_artist(artist))
    if title:
        data = _get(base + "&method=track.gettoptags" + a + "&track=" + urllib.parse.quote(str(title)))
    else:
        data = _get(base + "&method=artist.gettoptags" + a)
    tags = (data.get("toptags") or {}).get("tag") or []
    if isinstance(tags, dict):
        tags = [tags]
    return [(t.get("name", ""), float(t.get("count") or 0)) for t in tags[:15]]


def musicbrainz_tags(artist: str) -> List[Tuple[str, float]]:
    name = _first_artist(artist)
    if not name:
        return []
    q = urllib.parse.quote(f'artist:"{name}"')
    hits = _mb_get(f"https://musicbrainz.org/ws/2/artist/?query={q}&fmt=json&limit=5").get("artists", [])
    same = [h for h in hits if same_artist(h.get("name", ""), name)
            or any(same_artist(al.get("name", ""), name) for al in h.get("aliases", []) or [])]
    if not same:
        return []
    # Several artists can share a name; the best-known one has the most tag votes
    best = max(same, key=lambda h: (sum(t.get("count", 0) for t in h.get("tags", []) or []), int(h.get("score", 0))))
    tags = [(t.get("name", ""), float(t.get("count", 0) or 0)) for t in best.get("tags", []) or []]
    # Count 0 tags still carry information when nothing else is there
    return [(n, c if c > 0 else 0.5) for n, c in tags]


def deezer_tags(album_genres: Iterable[str]) -> List[Tuple[str, float]]:
    # Deezer lists the album's genres broad-first; give the first one most weight
    return [(g, 1.0 / (i + 1)) for i, g in enumerate(album_genres)]


# ---------------------------------------------------------------------------
# Cached lookup
# ---------------------------------------------------------------------------

def _cache_dir() -> Path:
    d = settings.DATA_DIR / "cache" / "genres"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path(kind: str, key: str) -> Path:
    return _cache_dir() / f"{kind}_{re.sub(r'[^a-z0-9]+', '_', key.lower())[:150]}.json"


def _cached(kind: str, key: str, fetch) -> Optional[List[str]]:
    p = _cache_path(kind, key)
    if p.exists():
        try:
            return json.loads(p.read_text())["genres"]
        except Exception:
            pass
    try:
        genres = summarise(fetch())
    except Exception:
        return None  # network trouble: don't cache, try again next time
    p.write_text(json.dumps({"genres": genres}))
    return genres


def lookup_genres(artist: str, title: Optional[str] = None,
                  deezer_album_genres: Optional[List[str]] = None) -> Tuple[List[str], str]:
    """Best genres for a song and which source they came from ("" if none)."""
    artist = str(artist or "").strip()
    if artist and os.getenv("LASTFM_API_KEY", "").strip():
        if title:
            g = _cached("lastfm_track", f"{_first_artist(artist)}|{title}", lambda: lastfm_tags(artist, title))
            if g:
                return g, "Last.fm"
        g = _cached("lastfm_artist", _first_artist(artist), lambda: lastfm_tags(artist))
        if g:
            return g, "Last.fm"
    if artist:
        g = _cached("musicbrainz", _first_artist(artist), lambda: musicbrainz_tags(artist))
        if g:
            return g, "MusicBrainz"
    if deezer_album_genres:
        g = summarise(deezer_tags(deezer_album_genres))
        if g:
            return g, "Deezer"
    return [], ""
