"""
Small games played on the maps people shared, and the weekly charts.

Galaxy quiz, two kinds of question mixed together:
  * "Which galaxy?"  A song from the atlas; pick the galaxy it lives in out of four.
  * "Why linked?"    Two songs joined by a hidden link on someone's map; pick what
                     joins them (played back to back, same playlists, musical match...).

The right answers stay on the server, and a run's score is counted there too, so
the leaderboard can't be filled by sending made-up scores.
"""
from __future__ import annotations

import random
import secrets
import threading
import time
from typing import Any, Dict, List, Optional

from app.core import atlas, map_share, store

ROUNDS = 10
QUESTION_TTL = 3600
HIDDEN_VIA = {
    "listening": "Played back to back", "playlists": "On the same playlists", "sound": "A musical match",
    "tags": "A rare shared tag", "features": "A collaboration", "artist": "The same artist",
    "album": "The same album", "border": "Next-door neighbours",
}

_questions: Dict[str, Dict[str, Any]] = {}
_runs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def _expire() -> None:
    cutoff = time.time() - QUESTION_TTL
    for d in (_questions, _runs):
        for k in [k for k, v in d.items() if v["at"] < cutoff]:
            d.pop(k, None)


def _galaxy_question(rng: random.Random) -> Optional[Dict[str, Any]]:
    a = atlas.get()
    clusters = [c for c in a.get("clusters", []) if c.get("size", 0) >= 3]
    if len(clusters) < 4:
        return None
    tracks = a.get("tracks", [])
    t = rng.choice(tracks)
    right = next(c for c in a["clusters"] if c["id"] == t["cluster"])
    others = rng.sample([c for c in clusters if c["id"] != right["id"]], 3)
    options = [right, *others]
    rng.shuffle(options)
    return {
        "kind": "galaxy",
        "prompt": "Which galaxy is this song in on the community atlas?",
        "song": {k: t.get(k) for k in ("title", "artist", "genre", "bpm", "key", "year")},
        "options": [{"id": str(c["id"]), "label": c.get("name") or c["label"], "hint": c.get("label")} for c in options],
        "answer": str(right["id"]),
        "explain": f"It sits in {right.get('name')}, the {right.get('label')} part of the atlas.",
    }


def _link_question(rng: random.Random) -> Optional[Dict[str, Any]]:
    metas = [m for m in map_share.all_listed()]
    rng.shuffle(metas)
    for meta in metas[:8]:
        found = map_share.get(meta["id"])
        hidden = [h for h in (found or {}).get("map", {}).get("hidden_connections", []) if h.get("via") in HIDDEN_VIA]
        if not hidden:
            continue
        h = rng.choice(hidden)
        tracks = {t["id"]: t for t in found["map"]["tracks"]}
        a, b = tracks.get(h["source"]), tracks.get(h["target"])
        if not a or not b:
            continue
        wrong = rng.sample([v for v in HIDDEN_VIA if v != h["via"]], 3)
        options = [h["via"], *wrong]
        rng.shuffle(options)
        return {
            "kind": "link",
            "prompt": f"On “{meta.get('title')}”, these two songs from different galaxies are linked. Why?",
            "pair": [{k: t.get(k) for k in ("title", "artist", "genre")} for t in (a, b)],
            "options": [{"id": v, "label": HIDDEN_VIA[v]} for v in options],
            "answer": h["via"],
            "explain": "; ".join(h.get("reasons") or []) or HIDDEN_VIA[h["via"]],
            "share_id": meta["id"],
        }
    return None


def question(listener: str) -> Dict[str, Any]:
    """The next question of this listener's run (a new run starts after ROUNDS)."""
    rng = random.Random(secrets.randbits(64))
    q = None
    for maker in rng.sample([_galaxy_question, _link_question], 2):
        q = maker(rng)
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
