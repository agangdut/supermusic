"""
"This week on your map": a weekly round-up for a signed-in listener.

  * Rediscover: songs from your own library you rarely play, a fresh handful each
    week (picked by the week number, so it stays the same all week).
  * New listeners like you: maps listed this week whose taste is closest to yours.
  * Your songs, fixed: song stats other listeners corrected this week, on songs
    in your library.
  * From people you follow: maps they shared this week.
  * You: new followers and upvotes on your maps this week.

It's shown on the Feed page. There's no email yet (that needs a mail server).
"""
from __future__ import annotations

import datetime as dt
import json
import random
import time
from typing import Any, Dict, Optional

import pandas as pd

from app.core import map_share, social, store, taste_match
from app.core.library_import import song_key
from app.core.music_map import _find

WEEK = 7 * 86400


def week_label(now: Optional[float] = None) -> str:
    d = dt.date.fromtimestamp(now or time.time())
    start = d - dt.timedelta(days=d.weekday())
    return f"Week of {start.strftime('%d %b %Y').lstrip('0')}"


def rediscover(df: pd.DataFrame, n: int = 8, now: Optional[float] = None) -> list:
    t_col, a_col, p_col = _find(df, "title"), _find(df, "artist"), _find(df, "plays")
    if t_col is None:
        return []
    rows = df.dropna(subset=[t_col])
    if p_col:
        plays = pd.to_numeric(rows[p_col], errors="coerce").fillna(0)
        cutoff = plays.quantile(0.4)
        rows = rows[plays <= cutoff]
    year, week, _ = dt.date.fromtimestamp(now or time.time()).isocalendar()
    rng = random.Random(year * 100 + week)
    idx = list(rows.index)
    rng.shuffle(idx)
    out = []
    for i in idx[:n]:
        r = rows.loc[i]
        out.append({"title": str(r[t_col]), "artist": str(r[a_col]) if a_col and pd.notna(r[a_col]) else None,
                    "plays": int(r[p_col]) if p_col and pd.notna(pd.to_numeric(r[p_col], errors="coerce")) else None})
    return out


def digest(username: str, df: Optional[pd.DataFrame]) -> Dict[str, Any]:
    now = time.time()
    since = now - WEEK
    c = store.connect()
    out: Dict[str, Any] = {"week": week_label(now), "has_library": df is not None}

    if df is not None:
        out["rediscover"] = rediscover(df, now=now)
        fresh = {m["id"] for m in map_share.all_listed() if m.get("created", 0) >= since}
        out["new_matches"] = [m for m in taste_match.matches(df, limit=30)
                              if m["share_id"] in fresh and map_share.owner_of(m["share_id"]) != username][:5]
        t_col, a_col = _find(df, "title"), _find(df, "artist")
        keys = []
        if t_col is not None:
            artists = df[a_col] if a_col else [""] * len(df)
            keys = sorted({song_key(a, t) for a, t in zip(artists, df[t_col]) if pd.notna(t)})
        fixes = []
        for i in range(0, len(keys), 500):
            chunk = keys[i:i + 500]
            marks = ",".join("?" * len(chunk))
            fixes += c.execute(
                f"SELECT v.field, v.value, v.created_at, s.artist, s.title FROM song_votes v "
                f"LEFT JOIN songs s ON s.song_key = v.song_key WHERE v.song_key IN ({marks}) "
                f"AND v.created_at > ? AND v.voter != ?", (*chunk, since, f"user:{username}")).fetchall()
        fixes.sort(key=lambda r: -r["created_at"])
        out["fixes"] = {"count": len(fixes), "recent": [
            {"field": r["field"], "value": json.loads(r["value"]), "title": r["title"], "artist": r["artist"]}
            for r in fixes[:6]]}

    people = social.following(username)
    if people:
        marks = ",".join("?" * len(people))
        rows = c.execute(f"SELECT * FROM events WHERE kind = 'shared_map' AND actor IN ({marks}) AND created_at > ? "
                         f"ORDER BY created_at DESC LIMIT 10", (*people, since)).fetchall()
        names = social.display_names([r["actor"] for r in rows])
        out["from_following"] = [{"actor": r["actor"], "actor_name": names.get(r["actor"], r["actor"]),
                                  **json.loads(r["payload"])} for r in rows]
    else:
        out["from_following"] = []

    out["new_followers"] = c.execute("SELECT COUNT(*) FROM follows WHERE followee = ? AND created_at > ?",
                                     (username, since)).fetchone()[0]
    mine = [m["id"] for m in map_share.by_owner(username, include_unlisted=True)]
    out["upvotes"] = sum(v["votes"] for v in map_share.votes(mine, None, since=since).values()) if mine else 0
    return out
