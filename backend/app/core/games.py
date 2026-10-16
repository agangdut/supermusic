"""
Small games played on the maps people shared, and the weekly charts.

Music quiz: ten questions with one right answer each, drawn from the songs on the
community atlas (every publicly listed library):
  * "What year did <artist> release <song or album>?"
  * "Who recorded <song>?"
  * "Which album is <song> on?"
  * "What kind of music does <artist> make?"
  * "Which of these came out first?"

The right answers stay on the server, and a run's score is counted there too, so
the leaderboard can't be filled by sending made-up scores.
"""
from __future__ import annotations

import datetime as _dt
import random
import secrets
import threading
import time
from collections import Counter
from typing import Any, Dict, List, Optional

from app.core import atlas, map_share, store

ROUNDS = 10
QUESTION_TTL = 3600

_questions: Dict[str, Dict[str, Any]] = {}
_runs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def _expire() -> None:
    cutoff = time.time() - QUESTION_TTL
    for d in (_questions, _runs):
        for k in [k for k, v in d.items() if v["at"] < cutoff]:
            d.pop(k, None)


def _text(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s.lower() not in ("nan", "none", "unknown") else None


def _year(v: Any) -> Optional[int]:
    try:
        y = int(str(v)[:4])
    except (TypeError, ValueError):
        return None
    return y if 1900 < y <= _dt.date.today().year else None


def _pool() -> List[Dict[str, Any]]:
    """Every song on the atlas once, with the facts we know about it."""
    seen, out = set(), []
    for t in atlas.get().get("tracks", []):
        title, artist = _text(t.get("title")), _text(t.get("artist"))
        if not title or not artist:
            continue
        key = (title.lower(), artist.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": title, "artist": artist, "album": _text(t.get("album")),
                    "genre": _text(t.get("genre")), "year": _year(t.get("year"))})
    return out


def _options(right: str, wrong: List[str], rng: random.Random) -> Optional[List[Dict[str, str]]]:
    wrong = list(dict.fromkeys(w for w in wrong if w and w.lower() != right.lower()))
    if len(wrong) < 3:
        return None
    opts = [right, *rng.sample(wrong, 3)]
    rng.shuffle(opts)
    return [{"id": o, "label": o} for o in opts]


def _year_question(pool, rng) -> Optional[Dict[str, Any]]:
    songs = [s for s in pool if s["year"]]
    if not songs:
        return None
    s = rng.choice(songs)
    this_year = _dt.date.today().year
    near = [y for y in range(s["year"] - 8, s["year"] + 9) if y != s["year"] and 1900 < y <= this_year]
    opts = _options(str(s["year"]), [str(y) for y in near], rng)
    if not opts:
        return None
    opts.sort(key=lambda o: o["id"])
    if s["album"] and rng.random() < 0.5:
        prompt = f"What year did {s['artist']} release the album “{s['album']}”?"
        explain = f"“{s['album']}” came out in {s['year']}."
    else:
        prompt = f"What year did {s['artist']} release “{s['title']}”?"
        explain = f"“{s['title']}” came out in {s['year']}."
    return {"kind": "year", "prompt": prompt, "song": {"title": s["title"], "artist": s["artist"], "album": s["album"], "genre": s["genre"]},
            "options": opts, "answer": str(s["year"]), "explain": explain}


def _artist_question(pool, rng) -> Optional[Dict[str, Any]]:
    s = rng.choice(pool)
    same_title = {p["artist"].lower() for p in pool if p["title"].lower() == s["title"].lower()}
    alike = [p["artist"] for p in pool if p["genre"] == s["genre"] and p["artist"].lower() not in same_title]
    others = [p["artist"] for p in pool if p["artist"].lower() not in same_title]
    wrong = list(dict.fromkeys(alike)) if len(set(alike)) >= 3 else list(dict.fromkeys(others))
    opts = _options(s["artist"], wrong, rng)
    if not opts:
        return None
    return {"kind": "artist", "prompt": f"Who recorded “{s['title']}”?",
            "song": {"title": s["title"], "album": s["album"], "year": s["year"], "genre": s["genre"]},
            "options": opts, "answer": s["artist"], "explain": f"It's by {s['artist']}."}


def _album_question(pool, rng) -> Optional[Dict[str, Any]]:
    songs = [s for s in pool if s["album"]]
    if not songs:
        return None
    s = rng.choice(songs)
    own = [p["album"] for p in songs if p["artist"].lower() == s["artist"].lower()]
    wrong = [a for a in own if a.lower() != s["album"].lower()] + [p["album"] for p in songs]
    opts = _options(s["album"], list(dict.fromkeys(wrong)), rng)
    if not opts:
        return None
    return {"kind": "album", "prompt": f"Which album is “{s['title']}” by {s['artist']} on?",
            "song": {"title": s["title"], "artist": s["artist"], "year": s["year"]},
            "options": opts, "answer": s["album"], "explain": f"It's on “{s['album']}”."}


def _genre_question(pool, rng) -> Optional[Dict[str, Any]]:
    by_artist: Dict[str, Counter] = {}
    for p in pool:
        if p["genre"]:
            by_artist.setdefault(p["artist"], Counter())[p["genre"]] += 1
    artists = [a for a, c in by_artist.items() if sum(c.values()) >= 2]
    if not artists:
        return None
    artist = rng.choice(artists)
    genre = by_artist[artist].most_common(1)[0][0]
    theirs = {g.lower() for g in by_artist[artist]}
    wrong = [p["genre"] for p in pool if p["genre"] and p["genre"].lower() not in theirs]
    opts = _options(genre, wrong, rng)
    if not opts:
        return None
    songs = [p["title"] for p in pool if p["artist"] == artist][:3]
    return {"kind": "genre", "prompt": f"What kind of music does {artist} make?",
            "song": {"artist": artist, "songs": songs}, "options": opts, "answer": genre,
            "explain": f"Mostly {genre}."}


def _first_question(pool, rng) -> Optional[Dict[str, Any]]:
    by_year: Dict[int, Dict[str, Any]] = {}
    for p in rng.sample(pool, len(pool)):
        if p["year"] and p["year"] not in by_year:
            by_year[p["year"]] = p
    if len(by_year) < 4:
        return None
    picks = rng.sample(list(by_year.values()), 4)
    oldest = min(picks, key=lambda p: p["year"])
    label = lambda p: f"“{p['title']}” by {p['artist']}"
    opts = [{"id": label(p), "label": label(p)} for p in picks]
    order = ", ".join(f"{p['title']} {p['year']}" for p in sorted(picks, key=lambda p: p["year"]))
    return {"kind": "first", "prompt": "Which of these came out first?", "options": opts,
            "answer": label(oldest), "explain": order + "."}


MAKERS = [(_year_question, 3), (_artist_question, 2), (_album_question, 2), (_genre_question, 1), (_first_question, 2)]


def question(listener: str) -> Dict[str, Any]:
    """The next question of this listener's run (a new run starts after ROUNDS)."""
    rng = random.Random(secrets.randbits(64))
    pool = _pool()
    q = None
    if len(pool) >= 8:
        makers = [m for m, w in MAKERS for _ in range(w)]
        rng.shuffle(makers)
        for maker in dict.fromkeys(makers):
            q = maker(pool, rng)
            if q:
                break
    if not q:
        raise LookupError("There aren't enough public maps to play yet. List yours on Shared maps to get it going.")
    qid = secrets.token_urlsafe(8)
    with _lock:
        _expire()
        run = _runs.get(listener)
        if not run or run["asked"] >= ROUNDS:
            run = _runs[listener] = {"score": 0, "asked": 0, "answered": 0, "at": time.time()}
        run["asked"] += 1
        run["at"] = time.time()
        _questions[qid] = {"listener": listener, "answer": q.pop("answer"), "explain": q.pop("explain"),
                           "at": time.time()}
        return {"id": qid, "round": run["asked"], "rounds": ROUNDS, "score": run["score"], **q}


def answer(listener: str, qid: str, choice: str) -> Dict[str, Any]:
    with _lock:
        q = _questions.pop(qid, None)
        if not q or q["listener"] != listener:
            raise LookupError("That question has expired. Here's a new one.")
        run = _runs.setdefault(listener, {"score": 0, "asked": 1, "answered": 0, "at": time.time()})
        right = choice == q["answer"]
        run["answered"] += 1
        if right:
            run["score"] += 1
        done = run["answered"] >= ROUNDS
        return {"correct": right, "answer": q["answer"], "explain": q["explain"], "score": run["score"],
                "round": run["answered"], "rounds": ROUNDS, "done": done}


def finish(listener: str, name: Optional[str]) -> Dict[str, Any]:
    """Save a finished run on the leaderboard."""
    with _lock:
        run = _runs.pop(listener, None)
    if not run or run["answered"] < ROUNDS:
        raise ValueError("Finish all the rounds first.")
    store.connect().execute(
        "INSERT INTO quiz_scores (listener, name, score, rounds, created_at) VALUES (?, ?, ?, ?, ?)",
        (listener, (name or "").strip()[:40] or None, run["score"], ROUNDS, time.time()))
    return {"score": run["score"], "rounds": ROUNDS}


def quiz_leaders(days: int = 7, limit: int = 10) -> List[Dict[str, Any]]:
    rows = store.connect().execute(
        "SELECT listener, MAX(name) AS name, MAX(score) AS best, COUNT(*) AS runs FROM quiz_scores "
        "WHERE created_at > ? GROUP BY listener ORDER BY best DESC, runs DESC LIMIT ?",
        (time.time() - days * 86400, limit)).fetchall()
    out = []
    for r in rows:
        who = r["listener"]
        name = r["name"] or (who[5:] if who.startswith("user:") else "A listener")
        out.append({"name": name, "username": who[5:] if who.startswith("user:") else None,
                    "best": r["best"], "runs": r["runs"], "rounds": ROUNDS})
    return out


# ---- radio charts --------------------------------------------------------------------------

def radio_played(station: str, label: str, share_id: Optional[str], listener: str) -> None:
    c = store.connect()
    # One count per listener per station per hour
    if c.execute("SELECT 1 FROM radio_plays WHERE station = ? AND listener = ? AND created_at > ?",
                 (station, listener, time.time() - 3600)).fetchone():
        return
    c.execute("INSERT INTO radio_plays (station, label, share_id, listener, created_at) VALUES (?, ?, ?, ?, ?)",
              (station[:200], label[:120], share_id, listener, time.time()))


def radio_charts(days: int = 7, limit: int = 10) -> List[Dict[str, Any]]:
    rows = store.connect().execute(
        "SELECT station, MAX(label) AS label, MAX(share_id) AS share_id, COUNT(*) AS plays, "
        "COUNT(DISTINCT listener) AS listeners FROM radio_plays WHERE created_at > ? "
        "GROUP BY station ORDER BY listeners DESC, plays DESC LIMIT ?",
        (time.time() - days * 86400, limit)).fetchall()
    titles = {}
    for r in rows:
        if r["share_id"] and r["share_id"] not in titles:
            m = map_share.read_meta(r["share_id"])
            titles[r["share_id"]] = (m or {}).get("title")
    return [{"station": r["station"], "label": r["label"], "share_id": r["share_id"],
             "map_title": titles.get(r["share_id"]), "plays": r["plays"], "listeners": r["listeners"]} for r in rows]
