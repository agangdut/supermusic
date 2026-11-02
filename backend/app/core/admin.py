"""
Running the site: who is an admin, reports from visitors, and visitor stats.

  * Admins are the usernames in SM_ADMINS (comma separated), e.g. SM_ADMINS=agangdut.
    Make the account on the site first, then add its name and restart the backend.
  * Anyone can report a shared map, a profile, a note pinned on the atlas or an
    artist's track. Reports wait on the admin page, where an admin removes the
    thing or dismisses the report.
  * Visitor stats count page views without cookies and without keeping IP
    addresses: each view stores a hash of (address, browser, today's date, a
    server secret), which tells visitors apart within a day but can't be turned
    back into an address or followed from one day to the next.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
import shutil
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.core import artist, constellations, map_share, social, store

KINDS = ("map", "profile", "pin", "track", "constellation")
REASONS = {
    "spam": "Spam or advertising",
    "offensive": "Hateful, abusive or sexual",
    "copyright": "Copyright",
    "personal": "Someone's private information",
    "other": "Something else",
}
KEEP_VIEWS_DAYS = 400
BOT_RE = re.compile(r"bot|crawl|spider|slurp|preview|facebookexternalhit|headless|python|curl|wget|httpx", re.I)


def admins() -> List[str]:
    return [a.strip().lower() for a in os.getenv("SM_ADMINS", "").split(",") if a.strip()]


def is_admin(username: Optional[str]) -> bool:
    return bool(username) and username.lower() in admins()


# ---- reports ------------------------------------------------------------------------------

def _target(kind: str, target: str) -> Optional[Dict[str, Any]]:
    """What a report points at, for the admin page; None when it's gone."""
    if kind == "map":
        meta = map_share.read_meta(target)
        if not meta:
            return None
        return {"title": meta.get("title"), "by": meta.get("by"), "owner": meta.get("owner"),
                "listed": bool(meta.get("listed")), "link": f"/s/{target}"}
    if kind == "profile":
        u = social.user_row(target)
        if not u:
            return None
        return {"title": u.get("display_name") or u["username"], "text": u.get("bio") or "",
                "owner": u["username"], "link": f"/u/{u['username']}"}
    if kind == "pin":
        if not str(target).isdigit():
            return None
        r = store.connect().execute("SELECT * FROM atlas_pins WHERE id = ?", (int(target),)).fetchone()
        if not r:
            return None
        a = r["author"]
        return {"title": r["song_key"], "text": r["text"], "owner": a[5:] if a.startswith("user:") else None,
                "author": a, "link": "/atlas"}
    if kind == "track":
        t = artist.get(target)
        if not t:
            return None
        return {"title": t.get("title"), "by": t.get("artist"), "owner": t.get("owner"),
                "listed": bool(t.get("public")), "link": f"/atlas?track={target}"}
    if kind == "constellation":
        if not str(target).isdigit():
            return None
        r = store.connect().execute("SELECT * FROM atlas_constellations WHERE id = ?", (int(target),)).fetchone()
        if not r:
            return None
        a = r["author"]
        return {"title": r["name"], "owner": a[5:] if a.startswith("user:") else None, "author": a,
                "link": f"/atlas?constellation={target}"}
    return None


def report(kind: str, target: str, reason: str, details: Optional[str], reporter: str) -> Dict[str, Any]:
    if kind not in KINDS:
        raise ValueError("Unknown kind of thing to report.")
    if reason not in REASONS:
        raise ValueError("Pick a reason.")
    target = str(target).strip()
    if _target(kind, target) is None:
        raise LookupError("That's already gone.")
    c = store.connect()
    open_one = c.execute("SELECT id FROM reports WHERE kind = ? AND target = ? AND reporter = ? AND status = 'open'",
                         (kind, target, reporter)).fetchone()
    if open_one:
        return {"id": open_one["id"], "already": True}
    today = c.execute("SELECT COUNT(*) FROM reports WHERE reporter = ? AND created_at > ?",
                      (reporter, time.time() - 86400)).fetchone()[0]
    if today >= 30:
        raise ValueError("That's a lot of reports today. Try again tomorrow.")
    cur = c.execute("INSERT INTO reports (kind, target, reason, details, reporter, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (kind, target, reason, (details or "").strip()[:1000] or None, reporter, time.time()))
    return {"id": cur.lastrowid, "already": False}


def reports(status: str = "open", limit: int = 200) -> List[Dict[str, Any]]:
    """Reports grouped by the thing reported, most reported first (open) or newest first."""
    rows = store.connect().execute(
        "SELECT * FROM reports WHERE status = ? ORDER BY created_at DESC LIMIT ?", (status, limit * 5)).fetchall()
    groups: Dict[tuple, Dict[str, Any]] = {}
    for r in rows:
        key = (r["kind"], r["target"])
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"id": r["id"], "kind": r["kind"], "target": r["target"], "count": 0, "reasons": {},
                               "notes": [], "first": r["created_at"], "last": r["created_at"],
                               "resolved_by": r["resolved_by"], "resolved_at": r["resolved_at"]}
        g["count"] += 1
        g["reasons"][r["reason"]] = g["reasons"].get(r["reason"], 0) + 1
        if r["details"] and len(g["notes"]) < 5:
            g["notes"].append(r["details"])
        g["first"] = min(g["first"], r["created_at"])
    out = list(groups.values())[:limit]
    for g in out:
        g["item"] = _target(g["kind"], g["target"])
    if status == "open":
        out.sort(key=lambda g: (-g["count"], -g["last"]))
    return out


def open_count() -> int:
    return store.connect().execute(
        "SELECT COUNT(DISTINCT kind || ':' || target) FROM reports WHERE status = 'open'").fetchone()[0]


def remove(kind: str, target: str) -> bool:
    """Take the thing down. A profile keeps its account but loses its name and bio."""
    c = store.connect()
    if kind == "map":
        f = map_share._folder(target)
        if not f:
            return False
        shutil.rmtree(f, ignore_errors=True)
        c.execute("DELETE FROM map_votes WHERE share_id = ?", (target,))
        return True
    if kind == "profile":
        return c.execute("UPDATE users SET display_name = NULL, bio = NULL WHERE username = ?",
                         (target,)).rowcount > 0
    if kind == "pin":
        return str(target).isdigit() and c.execute("DELETE FROM atlas_pins WHERE id = ?", (int(target),)).rowcount > 0
    if kind == "track":
        return c.execute("DELETE FROM artist_tracks WHERE id = ?", (target,)).rowcount > 0
    if kind == "constellation":
        return str(target).isdigit() and constellations.remove(int(target))
    return False


def resolve(report_id: int, action: str, admin: str) -> Dict[str, Any]:
    """action "remove" takes the thing down, "dismiss" keeps it. Either closes every open
    report about the same thing."""
    if action not in ("remove", "dismiss"):
        raise ValueError("Choose remove or dismiss.")
    c = store.connect()
    r = c.execute("SELECT kind, target FROM reports WHERE id = ?", (report_id,)).fetchone()
    if not r:
        raise LookupError("No such report.")
    removed = remove(r["kind"], r["target"]) if action == "remove" else False
    c.execute("UPDATE reports SET status = ?, resolved_by = ?, resolved_at = ? WHERE kind = ? AND target = ? AND status = 'open'",
              ("removed" if action == "remove" else "dismissed", admin, time.time(), r["kind"], r["target"]))
    return {"kind": r["kind"], "target": r["target"], "action": action, "removed": removed}


# ---- visitor stats ------------------------------------------------------------------------

def _today() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def _visitor(ip: str, user_agent: str, day: str) -> str:
    secret = os.getenv("JWT_SECRET_KEY", "supermusic")
    return hashlib.sha256(f"{secret}|{day}|{ip}|{user_agent}".encode()).hexdigest()[:16]


def _clean_path(path: str) -> Optional[str]:
    path = (path or "").split("?")[0].split("#")[0].strip()
    if not path.startswith("/") or len(path) > 120 or not re.fullmatch(r"[A-Za-z0-9/\[\]_.\-]*", path):
        return None
    return path


def _referrer(ref: Optional[str], own_host: Optional[str]) -> Optional[str]:
    try:
        host = (urlparse(ref or "").hostname or "").lower()
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    own = (own_host or "").split(":")[0].lower().removeprefix("www.")
    return host[:100] if host and host != own else None


def record_view(path: str, referrer: Optional[str], ip: str, user_agent: str, own_host: Optional[str]) -> bool:
    """Count one page view. False (nothing kept) for bots and odd paths."""
    path = _clean_path(path)
    if not path or not user_agent or BOT_RE.search(user_agent):
        return False
    day = _today()
    c = store.connect()
    c.execute("INSERT INTO page_views (day, path, visitor, referrer, created_at) VALUES (?, ?, ?, ?, ?)",
              (day, path, _visitor(ip, user_agent, day), _referrer(referrer, own_host), time.time()))
    if int(time.time()) % 500 == 0:  # now and then, forget views older than about a year
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=KEEP_VIEWS_DAYS)).strftime("%Y-%m-%d")
        c.execute("DELETE FROM page_views WHERE day < ?", (cutoff,))
    return True


def stats(days: int = 30) -> Dict[str, Any]:
    """Visitors and page views per day, top pages and sites people came from, plus totals."""
    days = max(1, min(days, 365))
    c = store.connect()
    start_dt = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days - 1)
    start = start_dt.strftime("%Y-%m-%d")
    since = dt.datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp()
    per_day = {r["day"]: {"visitors": r["visitors"], "views": r["views"]} for r in c.execute(
        "SELECT day, COUNT(DISTINCT visitor) AS visitors, COUNT(*) AS views FROM page_views WHERE day >= ? GROUP BY day",
        (start,))}
    signups = {r["day"]: r["n"] for r in c.execute(
        "SELECT strftime('%Y-%m-%d', created_at, 'unixepoch') AS day, COUNT(*) AS n FROM users "
        "WHERE created_at >= ? GROUP BY day", (since,))}
    jobs = {r["day"]: r["n"] for r in c.execute(
        "SELECT strftime('%Y-%m-%d', updated_at, 'unixepoch') AS day, COUNT(*) AS n FROM jobs "
        "WHERE updated_at >= ? GROUP BY day", (since,))}
    series = []
    for i in range(days):
        d = (start_dt + dt.timedelta(days=i)).strftime("%Y-%m-%d")
        series.append({"day": d, **per_day.get(d, {"visitors": 0, "views": 0}),
                       "signups": signups.get(d, 0), "jobs": jobs.get(d, 0)})
    top_pages = [dict(r) for r in c.execute(
        "SELECT path, COUNT(*) AS views, COUNT(DISTINCT day || visitor) AS visitors FROM page_views "
        "WHERE day >= ? GROUP BY path ORDER BY views DESC LIMIT 15", (start,))]
    referrers = [dict(r) for r in c.execute(
        "SELECT referrer, COUNT(DISTINCT day || visitor) AS visitors FROM page_views "
        "WHERE day >= ? AND referrer IS NOT NULL GROUP BY referrer ORDER BY visitors DESC LIMIT 10", (start,))]
    totals = c.execute(
        "SELECT COUNT(DISTINCT day || visitor) AS visitors, COUNT(*) AS views FROM page_views WHERE day >= ?",
        (start,)).fetchone()
    shared = map_share._all_metas()
    return {
        "days": days,
        "series": series,
        "top_pages": top_pages,
        "referrers": referrers,
        "totals": {
            "visitors": totals["visitors"], "views": totals["views"],
            "signups": sum(signups.values()), "jobs": sum(jobs.values()),
            "accounts": c.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "shared_maps": len(shared), "listed_maps": sum(1 for m in shared if m.get("listed")),
            "open_reports": open_count(),
        },
    }
