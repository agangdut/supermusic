"""
The people side of SuperMusic: profiles, follows, the feed and reputation.

Everything lives in the shared SQLite file (app/core/store.py).

  * A profile is an account (users table) plus the maps it shared while signed in.
  * Following someone puts what they do in your feed: maps they share, songs they
    pin notes on, tracks they put on the atlas.
  * Events about you (someone followed you, upvoted or compared with your map, a
    song fix of yours was agreed) also land in your feed.
  * Reputation is earned by helping the shared data: song fixes that other
    listeners ended up agreeing with count most, being the first to suggest a fix
    that was later agreed counts extra, and upvotes on your maps count a little.
"""
from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core import community, store

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,50}$")

# Reputation points
POINTS_AGREED = 10   # a fix of yours matches what listeners agreed on
POINTS_FIRST = 5     # ...and you were the first to suggest it
POINTS_FIX = 1       # any fix
POINTS_UPVOTE = 2    # an upvote on one of your maps
LEVELS = [(0, "Listener"), (25, "Tuner"), (100, "Curator"), (300, "Cartographer"), (1000, "Astronomer")]


def now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def user_row(username: str) -> Optional[Dict[str, Any]]:
    r = store.connect().execute(
        "SELECT username, email, created_at, display_name, bio, library_csv, library_title, is_artist "
        "FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
    return dict(r) if r else None


def public_user(u: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "username": u["username"],
        "display_name": u.get("display_name") or u["username"],
        "bio": u.get("bio") or "",
        "joined": u.get("created_at"),
        "is_artist": bool(u.get("is_artist")),
        "has_library": bool(u.get("library_csv")),
        "library_title": u.get("library_title"),
    }


def update_profile(username: str, display_name: Optional[str] = None, bio: Optional[str] = None,
                   is_artist: Optional[bool] = None) -> Dict[str, Any]:
    sets, args = [], []
    if display_name is not None:
        sets.append("display_name = ?")
        args.append(display_name.strip()[:40] or None)
    if bio is not None:
        sets.append("bio = ?")
        args.append(bio.strip()[:280] or None)
    if is_artist is not None:
        sets.append("is_artist = ?")
        args.append(1 if is_artist else 0)
    if sets:
        store.connect().execute(f"UPDATE users SET {', '.join(sets)} WHERE username = ?", (*args, username))
    return public_user(user_row(username))


def set_library(username: str, csv_path: Optional[str], title: Optional[str] = None) -> None:
    """Remember the library behind this person's own map (for compare and the weekly digest)."""
    store.connect().execute("UPDATE users SET library_csv = ?, library_title = ? WHERE username = ?",
                            (csv_path, title, username))


def display_names(usernames: List[str]) -> Dict[str, str]:
    names = sorted({u for u in usernames if u})
    if not names:
        return {}
    marks = ",".join("?" * len(names))
    rows = store.connect().execute(
        f"SELECT username, display_name FROM users WHERE username IN ({marks})", names).fetchall()
    return {r["username"]: r["display_name"] or r["username"] for r in rows}


def search_users(q: str, limit: int = 20) -> List[Dict[str, Any]]:
    like = f"%{q.strip()}%"
    rows = store.connect().execute(
        "SELECT username, email, created_at, display_name, bio, library_csv, library_title, is_artist FROM users "
        "WHERE username LIKE ? OR display_name LIKE ? ORDER BY created_at DESC LIMIT ?", (like, like, limit)).fetchall()
    return [public_user(dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# Follows
# ---------------------------------------------------------------------------

def follow(follower: str, followee: str, on: bool = True) -> Dict[str, Any]:
    if follower == followee:
        raise ValueError("You can't follow yourself.")
    if not user_row(followee):
        raise LookupError(followee)
    c = store.connect()
    if on:
        cur = c.execute("INSERT OR IGNORE INTO follows (follower, followee, created_at) VALUES (?, ?, ?)",
                        (follower, followee, now()))
        if cur.rowcount:
            log(follower, "followed", followee, {})
    else:
        c.execute("DELETE FROM follows WHERE follower = ? AND followee = ?", (follower, followee))
    return follow_counts(followee, follower)


def follow_counts(username: str, viewer: Optional[str] = None) -> Dict[str, Any]:
    c = store.connect()
    followers = c.execute("SELECT COUNT(*) FROM follows WHERE followee = ?", (username,)).fetchone()[0]
    following = c.execute("SELECT COUNT(*) FROM follows WHERE follower = ?", (username,)).fetchone()[0]
    mine = bool(viewer) and bool(c.execute("SELECT 1 FROM follows WHERE follower = ? AND followee = ?",
                                           (viewer, username)).fetchone())
    return {"followers": followers, "following": following, "you_follow": mine}


def following(username: str) -> List[str]:
    return [r[0] for r in store.connect().execute("SELECT followee FROM follows WHERE follower = ?", (username,))]


def follow_list(username: str, which: str = "followers") -> List[Dict[str, Any]]:
    col, other = ("followee", "follower") if which == "followers" else ("follower", "followee")
    rows = store.connect().execute(
        f"SELECT u.username, u.email, u.created_at, u.display_name, u.bio, u.library_csv, u.library_title, u.is_artist "
        f"FROM follows f JOIN users u ON u.username = f.{other} WHERE f.{col} = ? ORDER BY f.created_at DESC",
        (username,)).fetchall()
    return [public_user(dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# Events and the feed
# ---------------------------------------------------------------------------

def log(actor: str, kind: str, target: Optional[str], payload: Dict[str, Any]) -> None:
    """Record something for the feed. Never fails the action that caused it."""
    try:
        store.connect().execute(
            "INSERT INTO events (actor, kind, target, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (actor or "", kind, target, json.dumps(payload), now()))
    except Exception:
        pass


def _event(r) -> Dict[str, Any]:
    return {"id": r["id"], "actor": r["actor"], "kind": r["kind"], "target": r["target"],
            "data": json.loads(r["payload"] or "{}"), "at": r["created_at"]}


def feed(username: str, limit: int = 50, before: Optional[float] = None) -> List[Dict[str, Any]]:
    """What people you follow did, and what happened to you, newest first."""
    people = following(username)
    marks = ",".join("?" * len(people)) or "''"
    args: List[Any] = [*people, username, username]
    when = ""
    if before:
        when = "AND created_at < ?"
        args.append(before)
    rows = store.connect().execute(
        f"SELECT * FROM events WHERE ((actor IN ({marks}) AND kind != 'followed') OR target = ?) "
        f"AND actor != ? {when} ORDER BY created_at DESC LIMIT ?", (*args, limit)).fetchall()
    out = [_event(r) for r in rows]
    names = display_names([e["actor"] for e in out] + [e["target"] for e in out if e["target"]])
    for e in out:
        e["actor_name"] = names.get(e["actor"], e["actor"])
        e["target_name"] = names.get(e["target"], e["target"]) if e["target"] else None
    return out


def recent_public(limit: int = 30) -> List[Dict[str, Any]]:
    """Everyone's public actions (for people who don't follow anyone yet)."""
    rows = store.connect().execute(
        "SELECT * FROM events WHERE kind IN ('shared_map', 'pinned', 'artist_track') ORDER BY created_at DESC LIMIT ?",
        (limit,)).fetchall()
    out = [_event(r) for r in rows]
    names = display_names([e["actor"] for e in out])
    for e in out:
        e["actor_name"] = names.get(e["actor"], e["actor"])
    return out


# ---------------------------------------------------------------------------
# Reputation
# ---------------------------------------------------------------------------

def _level(points: int) -> Dict[str, Any]:
    name, floor, nxt = LEVELS[0][1], 0, None
    for i, (p, n) in enumerate(LEVELS):
        if points >= p:
            name, floor = n, p
            nxt = LEVELS[i + 1][0] if i + 1 < len(LEVELS) else None
    return {"level": name, "level_floor": floor, "next_level_at": nxt}


def _matches(field: str, mine: Any, agreed: Any) -> bool:
    if field == "vibes":
        return bool(set(mine or []) & set(agreed or []))
    if field in ("key", "genre"):
        return json.dumps(mine) == json.dumps(agreed)
    try:
        a, b = float(mine), float(agreed)
    except (TypeError, ValueError):
        return False
    if field == "bpm":
        a = community._fold(a, b)
    return community._close(field, a, b)


def reputation_for(voters: List[str], upvotes: Dict[str, int]) -> Dict[str, Dict[str, Any]]:
    """{username: {points, fixes, agreed, first, upvotes, level, badges}} for these usernames."""
    voters = [v for v in voters if v]
    if not voters:
        return {}
    c = store.connect()
    ids = [f"user:{v}" for v in voters]
    marks = ",".join("?" * len(ids))
    mine = c.execute(f"SELECT song_key, field, voter, value, created_at FROM song_votes WHERE voter IN ({marks})",
                     ids).fetchall()
    stats = {v: {"fixes": 0, "agreed": 0, "first": 0} for v in voters}
    songs = sorted({r["song_key"] for r in mine})
    all_rows: Dict[tuple, list] = defaultdict(list)
    for chunk in community._chunks(songs):
        m = ",".join("?" * len(chunk))
        for r in c.execute(f"SELECT song_key, field, voter, ip_hash, value, created_at FROM song_votes "
                           f"WHERE song_key IN ({m})", chunk):
            all_rows[(r["song_key"], r["field"])].append(r)
    agreed: Dict[tuple, Any] = {}
    first: Dict[tuple, str] = {}
    for k, rows in all_rows.items():
        values = community._one_per_listener(rows).get(k, [])
        a = community.agree(k[1], values)
        if a:
            agreed[k] = a["value"]
            earliest = min(rows, key=lambda r: r["created_at"])
            first[k] = earliest["voter"]
    for r in mine:
        u = r["voter"][5:]
        s = stats[u]
        s["fixes"] += 1
        k = (r["song_key"], r["field"])
        if k in agreed and _matches(r["field"], json.loads(r["value"]), agreed[k]):
            s["agreed"] += 1
            if first.get(k) == r["voter"]:
                s["first"] += 1
    out = {}
    for u, s in stats.items():
        up = int(upvotes.get(u, 0))
        points = s["agreed"] * POINTS_AGREED + s["first"] * POINTS_FIRST + s["fixes"] * POINTS_FIX + up * POINTS_UPVOTE
        badges = []
        if s["first"]:
            badges.append({"id": "first", "label": "First to tag", "hint": f"First to suggest {s['first']} fix(es) others agreed with"})
        if s["agreed"] >= 10:
            badges.append({"id": "trusted", "label": "Trusted ear", "hint": "10+ fixes that listeners agreed with"})
        if up >= 10:
            badges.append({"id": "popular", "label": "Crowd favourite", "hint": "10+ upvotes on shared maps"})
        out[u] = {"points": points, **s, "upvotes": up, **_level(points), "badges": badges}
    return out


def reputation(username: str, upvotes: int = 0) -> Dict[str, Any]:
    return reputation_for([username], {username: upvotes}).get(username) or {
        "points": 0, "fixes": 0, "agreed": 0, "first": 0, "upvotes": upvotes, **_level(0), "badges": []}


def top_contributors(owners_upvotes: Dict[str, int], limit: int = 20) -> List[Dict[str, Any]]:
    """Signed-in listeners with the most reputation."""
    c = store.connect()
    voters = [r[0][5:] for r in c.execute("SELECT DISTINCT voter FROM song_votes WHERE voter LIKE 'user:%'")]
    people = sorted(set(voters) | set(owners_upvotes))
    rep = reputation_for(people, owners_upvotes)
    names = display_names(people)
    rows = [{"username": u, "display_name": names.get(u, u), **r} for u, r in rep.items() if r["points"] > 0]
    rows.sort(key=lambda r: -r["points"])
    return rows[:limit]


def feed_of(username: str, limit: int = 20) -> List[Dict[str, Any]]:
    """One person's own public activity, for their profile."""
    rows = store.connect().execute(
        "SELECT * FROM events WHERE actor = ? AND kind IN ('shared_map', 'pinned', 'artist_track', 'followed') "
        "ORDER BY created_at DESC LIMIT ?", (username, limit)).fetchall()
    out = [_event(r) for r in rows]
    names = display_names([username] + [e["target"] for e in out if e["target"]])
    for e in out:
        e["actor_name"] = names.get(username, username)
        e["target_name"] = names.get(e["target"], e["target"]) if e["target"] else None
    return out


def delete_account(username: str) -> Dict[str, Any]:
    """Remove an account and what it made: shared maps, votes, follows, feed events, pins,
    uploaded artist tracks, quiz and radio history, and the library behind its own map."""
    from app.core import map_share
    from app.core.config import settings

    maps = [m["id"] for m in map_share.by_owner(username, include_unlisted=True)]
    for share_id in maps:
        map_share.delete(share_id, "", owner=username)
    u = user_row(username) or {}
    lib = u.get("library_csv")
    if lib:
        p = Path(lib).resolve()
        if p.is_file() and p.is_relative_to(settings.PROCESSED_DIR.resolve()):
            p.unlink(missing_ok=True)
    voter = f"user:{username}"
    with store.tx() as c:
        for sql, args in [
            ("DELETE FROM song_votes WHERE voter = ?", (voter,)),
            ("DELETE FROM map_votes WHERE voter = ?", (voter,)),
            ("DELETE FROM follows WHERE follower = ? OR followee = ?", (username, username)),
            ("DELETE FROM events WHERE actor = ? OR target = ?", (username, username)),
            ("DELETE FROM atlas_pins WHERE author = ?", (voter,)),
            ("DELETE FROM artist_tracks WHERE owner = ?", (username,)),
            ("DELETE FROM radio_plays WHERE listener IN (?, ?)", (voter, username)),
            ("DELETE FROM quiz_scores WHERE listener IN (?, ?)", (voter, username)),
            ("DELETE FROM users WHERE username = ?", (username,)),
        ]:
            c.execute(sql, args)
    return {"deleted": True, "maps": len(maps)}
