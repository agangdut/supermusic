"""Song constellations: stars on someone's Music Map joined by lines, with a name.

A constellation is a short path through songs, like the stick figure of a star sign.
Songs are stored by artist and title (not the map's star numbers), so a constellation
survives a re-import or a Remap, where every song gets a new number and a new spot.

    {"id": "k3x9a", "name": "Night drive", "color": "#7dd3fc",
     "stars": [{"artist": "...", "title": "..."}, ...], "created": 1730000000.0}

They come from the browser, so everything is checked here before it is saved on an
account or put into a shared map.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, List, Optional

from app.core import store

MAX_CONSTELLATIONS = 30
MAX_STARS = 40
MIN_STARS = 2
NAME_MAX = 40
TEXT_MAX = 200

ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,24}$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
DEFAULT_COLOR = "#7dd3fc"


def _text(v: Any, limit: int) -> str:
    return v.strip()[:limit] if isinstance(v, str) else ""


def clean(items: Any) -> List[dict]:
    """Keep only well-formed constellations; quietly drop the rest."""
    if not isinstance(items, list):
        return []
    out: List[dict] = []
    seen = set()
    for i, c in enumerate(items[:MAX_CONSTELLATIONS]):
        if not isinstance(c, dict):
            continue
        cid = c.get("id") if isinstance(c.get("id"), str) and ID_RE.match(c["id"]) else f"c{i}"
        if cid in seen:
            continue
        stars = []
        for s in (c.get("stars") if isinstance(c.get("stars"), list) else [])[:MAX_STARS]:
            if not isinstance(s, dict):
                continue
            title = _text(s.get("title"), TEXT_MAX)
            if title:
                stars.append({"artist": _text(s.get("artist"), TEXT_MAX), "title": title})
        if len(stars) < MIN_STARS:
            continue
        color = c.get("color") if isinstance(c.get("color"), str) and COLOR_RE.match(c["color"]) else DEFAULT_COLOR
        created = c.get("created")
        seen.add(cid)
        out.append({
            "id": cid,
            "name": _text(c.get("name"), NAME_MAX) or "Untitled",
            "color": color.lower(),
            "stars": stars,
            "created": float(created) if isinstance(created, (int, float)) and created > 0 else time.time(),
        })
    return out


def for_user(username: str) -> List[dict]:
    row = store.connect().execute("SELECT constellations FROM users WHERE username = ?", (username,)).fetchone()
    if not row or not row["constellations"]:
        return []
    try:
        return clean(json.loads(row["constellations"]))
    except ValueError:
        return []


def save_for_user(username: str, items: Any) -> List[dict]:
    """Replace this person's constellations (the browser always sends the whole list)."""
    cleaned = clean(items)
    store.connect().execute("UPDATE users SET constellations = ? WHERE username = ?",
                            (json.dumps(cleaned, separators=(",", ":")), username))
    return cleaned


# ---- Community atlas: proposed constellations that everyone votes on ----------------------
#
# Anyone signed in can propose a constellation on the atlas. Listeners vote yes or no, one
# vote each. With at least MIN_VOTES votes and APPROVE_SHARE of them yes, it becomes an
# official constellation that everyone sees on the atlas. The status is worked out from the
# votes every time, so one that loses support goes back to being a proposal.

MIN_VOTES = 5
APPROVE_SHARE = 0.8
MAX_PROPOSALS_PER_DAY = 3
MAX_VOTES_PER_NETWORK = 3  # per proposal, so one person can't vote from many browsers
KEY_MAX = 400


class ProposalError(ValueError):
    pass


def status_of(yes: int, no: int) -> str:
    total = yes + no
    return "official" if total >= MIN_VOTES and yes / total >= APPROVE_SHARE else "proposed"


def _proposal(r, counts: dict, mine: dict, names: dict) -> dict:
    yes, no = counts.get(r["id"], (0, 0))
    a = r["author"]
    user = a[5:] if a.startswith("user:") else None
    return {
        "id": r["id"], "name": r["name"], "color": r["color"], "song_keys": json.loads(r["song_keys"]),
        "created": r["created_at"], "author": names.get(user, user) if user else "a listener",
        "username": user, "yes": yes, "no": no, "status": status_of(yes, no), "my_vote": mine.get(r["id"]),
    }


def proposals(voter: Optional[str] = None, ids: Optional[List[int]] = None) -> List[dict]:
    """Every atlas constellation, official ones first, then the most voted proposals."""
    from app.core.social import display_names

    c = store.connect()
    if ids is None:
        rows = c.execute("SELECT * FROM atlas_constellations ORDER BY created_at DESC LIMIT 500").fetchall()
    else:
        rows = c.execute(f"SELECT * FROM atlas_constellations WHERE id IN ({','.join('?' * len(ids)) or 'NULL'})", ids).fetchall()
    counts = {r[0]: (r[1], r[2]) for r in c.execute(
        "SELECT constellation_id, SUM(up), SUM(1 - up) FROM atlas_constellation_votes GROUP BY constellation_id")}
    mine = {}
    if voter:
        mine = {r[0]: bool(r[1]) for r in c.execute(
            "SELECT constellation_id, up FROM atlas_constellation_votes WHERE voter = ?", (voter,))}
    names = display_names([r["author"][5:] for r in rows if r["author"].startswith("user:")])
    out = [_proposal(r, counts, mine, names) for r in rows]
    out.sort(key=lambda p: (p["status"] != "official", -(p["yes"] + p["no"]), -p["created"]))
    return out


def propose(author: str, name: Any, color: Any, song_keys: Any) -> dict:
    keys = []
    for k in song_keys if isinstance(song_keys, list) else []:
        if isinstance(k, str) and k.strip() and len(k) <= KEY_MAX:
            keys.append(k)
    keys = keys[:MAX_STARS]
    if len(keys) < MIN_STARS:
        raise ProposalError("Join at least two stars.")
    name = _text(name, NAME_MAX)
    if not name:
        raise ProposalError("Give your constellation a name.")
    color = color.lower() if isinstance(color, str) and COLOR_RE.match(color) else DEFAULT_COLOR
    c = store.connect()
    today = c.execute("SELECT COUNT(*) FROM atlas_constellations WHERE author = ? AND created_at > ?",
                      (author, time.time() - 86400)).fetchone()[0]
    if today >= MAX_PROPOSALS_PER_DAY:
        raise ProposalError(f"That's {MAX_PROPOSALS_PER_DAY} proposals today. Try again tomorrow.")
    cur = c.execute("INSERT INTO atlas_constellations (name, color, song_keys, author, created_at) VALUES (?, ?, ?, ?, ?)",
                    (name, color, json.dumps(keys), author, time.time()))
    return proposals(author, [cur.lastrowid])[0]


def vote(proposal_id: int, voter: str, ip: Optional[str], up: Optional[bool]) -> dict:
    """Yes (up=True), no (up=False), or take your vote back (None)."""
    with store.tx() as c:
        r = c.execute("SELECT author FROM atlas_constellations WHERE id = ?", (proposal_id,)).fetchone()
        if not r:
            raise LookupError(proposal_id)
        if r["author"] == voter:
            raise ProposalError("You can't vote on your own constellation.")
        if up is None:
            c.execute("DELETE FROM atlas_constellation_votes WHERE constellation_id = ? AND voter = ?", (proposal_id, voter))
        else:
            had = c.execute("SELECT 1 FROM atlas_constellation_votes WHERE constellation_id = ? AND voter = ?",
                            (proposal_id, voter)).fetchone()
            if not had and ip and c.execute(
                    "SELECT COUNT(*) FROM atlas_constellation_votes WHERE constellation_id = ? AND ip_hash = ?",
                    (proposal_id, ip)).fetchone()[0] >= MAX_VOTES_PER_NETWORK:
                raise ProposalError("This constellation already has several votes from your network.")
            c.execute("INSERT OR REPLACE INTO atlas_constellation_votes (constellation_id, voter, ip_hash, up, created_at) "
                      "VALUES (?, ?, ?, ?, ?)", (proposal_id, voter, ip, 1 if up else 0, time.time()))
    return proposals(voter, [proposal_id])[0]


def withdraw(proposal_id: int, author: str) -> bool:
    """The person who proposed it can take it down (votes go with it)."""
    with store.tx() as c:
        if not c.execute("DELETE FROM atlas_constellations WHERE id = ? AND author = ?", (proposal_id, author)).rowcount:
            return False
        c.execute("DELETE FROM atlas_constellation_votes WHERE constellation_id = ?", (proposal_id,))
    return True


def remove(proposal_id: int) -> bool:
    """Admins taking a reported constellation down."""
    with store.tx() as c:
        gone = c.execute("DELETE FROM atlas_constellations WHERE id = ?", (proposal_id,)).rowcount > 0
        c.execute("DELETE FROM atlas_constellation_votes WHERE constellation_id = ?", (proposal_id,))
    return gone
