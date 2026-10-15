"""
Library statistics for the Music Map's "Stats" panel.

Where the map shows how songs relate to each other, these numbers describe the
library as a whole: what's in it, what actually gets played, how that changed over
time, and short lists worth acting on (favourites you stopped playing, songs you
keep skipping, the odd ones out). Everything is computed from the same prepared
data as the map, so it costs well under a second even for 20,000+ songs.

"Library share" is the fraction of songs; "listening share" is the fraction of
plays (or of the engagement score when there are ratings/likes but no play counts).
Comparing the two is the interesting part: 10% of the library getting 40% of the
plays says more than either number alone.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


def _weights(p) -> Optional[np.ndarray]:
    """Plays when the file has them, otherwise the 0..1 engagement score, otherwise None."""
    if p.cols["plays"]:
        plays = pd.to_numeric(p.df[p.cols["plays"]], errors="coerce").fillna(0).clip(lower=0).to_numpy(dtype=float)
        if plays.sum() > 0:
            return plays
    if p.engagement is not None and p.engagement.sum() > 0:
        return p.engagement.astype(float)
    return None


def _breakdown(values: List[Any], w: Optional[np.ndarray], skips: Optional[np.ndarray] = None,
               plays: Optional[np.ndarray] = None, top: Optional[int] = None) -> List[Dict[str, Any]]:
    """Per value: song count, share of the library, share of the listening (and skip rate)."""
    s = pd.DataFrame({"v": values})
    s["w"] = w if w is not None else 0.0
    if skips is not None and plays is not None:
        s["skips"], s["plays"] = skips, plays
    s = s[s["v"].notna() & (s["v"] != "")]
    if s.empty:
        return []
    g = s.groupby("v", sort=False)
    out = pd.DataFrame({"songs": g.size(), "w": g["w"].sum()})
    if "skips" in s:
        out["skips"], out["plays"] = g["skips"].sum(), g["plays"].sum()
    total_songs, total_w = out["songs"].sum(), out["w"].sum()
    out = out.sort_values(["w", "songs"] if w is not None else ["songs"], ascending=False)
    if top:
        out = out.head(top)
    rows = []
    for v, r in out.iterrows():
        row = {"name": v, "songs": int(r["songs"]), "library_share": round(r["songs"] / total_songs, 3)}
        if w is not None and total_w > 0:
            row["listening_share"] = round(float(r["w"]) / total_w, 3)
        if "skips" in r and r["plays"] + r["skips"] >= 20:
            row["skip_rate"] = round(float(r["skips"] / (r["plays"] + r["skips"])), 3)
        rows.append(row)
    return rows


def _entropy(values: List[Any], w: Optional[np.ndarray] = None) -> Optional[float]:
    """0 = everything is one genre, 1 = spread evenly over every genre present."""
    s = pd.Series(w if w is not None else np.ones(len(values)), index=values)
    s = s[[v is not None and v != "" for v in values]]
    totals = s.groupby(level=0).sum()
    totals = totals[totals > 0]
    if len(totals) < 2:
        return None
    q = totals / totals.sum()
    return round(float(-(q * np.log(q)).sum() / math.log(len(q))), 3)


def library_stats(p, labels: np.ndarray, clusters: List[Dict[str, Any]], tracks: List[Dict[str, Any]],
                  nn_dist: np.ndarray) -> Dict[str, Any]:
    df, cols, n = p.df, p.cols, len(p.df)
    w = _weights(p)
    plays = skips = None
    if cols["plays"]:
        plays = pd.to_numeric(df[cols["plays"]], errors="coerce").fillna(0).clip(lower=0).to_numpy(dtype=float)
    if cols["skips"]:
        skips = pd.to_numeric(df[cols["skips"]], errors="coerce").fillna(0).clip(lower=0).to_numpy(dtype=float)
    top_genre = [g[0] if g else None for g in p.genres]

    # ---- overview -------------------------------------------------------------------
    overview: Dict[str, Any] = {
        "songs": n,
        "artists": len({a.lower() for a in p.artists if a}),
    }
    if cols["album"]:
        overview["albums"] = int(df[cols["album"]].dropna().astype(str).str.lower().nunique())
    if plays is not None:
        overview["plays"] = int(plays.sum())
        overview["never_played"] = int((plays == 0).sum()) if plays.sum() > 0 else None
    if skips is not None:
        overview["skips"] = int(skips.sum())
    minutes = next((c for c in df.columns if c.lower() == "minutes_played"), None)
    if minutes:
        overview["hours"] = round(float(pd.to_numeric(df[minutes], errors="coerce").sum()) / 60, 1)
    if cols["liked"]:
        overview["liked"] = sum(1 for t in tracks if t.get("liked"))
    dates = sorted(d for t in tracks for d in (t.get("first_played"), t.get("last_played")) if d)
    if dates:
        overview["first_date"], overview["last_date"] = dates[0], dates[-1]

    out: Dict[str, Any] = {"overview": overview}

    # ---- how concentrated the listening is -----------------------------------------
    if plays is not None and plays.sum() > 0:
        srt = np.sort(plays)[::-1]
        cum = np.cumsum(srt) / srt.sum()
        out["concentration"] = {
            "top_1pct_share": round(float(srt[: max(1, n // 100)].sum() / srt.sum()), 3),
            "top_10pct_share": round(float(srt[: max(1, n // 10)].sum() / srt.sum()), 3),
            "half_plays_songs": int(np.searchsorted(cum, 0.5) + 1),
        }

    # ---- diversity: how spread over genres the library and the listening are ------------
    if any(top_genre):
        out["diversity"] = {
            "genres": len({g for g in top_genre if g}),
            "library": _entropy(top_genre),
            "listening": _entropy(top_genre, w) if w is not None else None,
        }

    # ---- breakdowns ---------------------------------------------------------------------
    if any(top_genre):
        rows = _breakdown(top_genre, w, skips, plays, top=12)
        for r in rows:
            r["name"] = p.gname(r["name"])
        out["genres"] = rows
    if any(p.artists):
        out["top_artists"] = _breakdown([a or None for a in p.artists], w, top=12)
    years = [t.get("year") for t in tracks]
    if any(years):
        rows = _breakdown([f"{y // 10 * 10}s" if y else None for y in years], w)
        out["decades"] = sorted(rows, key=lambda r: r["name"])
    if any(p.keys):
        rows = _breakdown([k.camelot if k else None for k in p.keys], w)
        names = {k.camelot: k.name for k in p.keys if k}
        for r in rows:
            r["camelot"], r["name"] = r["name"], names[r["name"]]
        out["keys"] = sorted(rows, key=lambda r: (int(r["camelot"][:-1]), r["camelot"][-1]))
        out["modes"] = _breakdown(["minor" if k.minor else "major" if k else None for k in p.keys], w)
    if p.bpm is not None and np.isfinite(p.bpm).any():
        b = np.where((p.bpm >= 40) & (p.bpm <= 220), p.bpm, np.nan)
        rows = _breakdown([f"{int(x // 10 * 10)}" if np.isfinite(x) else None for x in b], w)
        for r in rows:
            r["lo"] = int(r["name"])
            r["name"] = f"{r['lo']}–{r['lo'] + 9}"
        out["tempo"] = sorted(rows, key=lambda r: r["lo"])

    # ---- discovery timeline: when songs entered your life, and which cluster -------------
    when = [t.get("first_played") or t.get("added") for t in tracks]
    if sum(1 for d in when if d) >= 10:
        span_years = int(max(d for d in when if d)[:4]) - int(min(d for d in when if d)[:4])
        by_month = span_years < 3
        period = [(d[:7] if by_month else d[:4]) if d else None for d in when]
        tl = pd.DataFrame({"period": period, "cluster": labels, "genre": top_genre}).dropna(subset=["period"])
        timeline = []
        for per, g in tl.groupby("period"):
            counts = g["cluster"].value_counts()
            genre = g["genre"].dropna().value_counts()
            timeline.append({
                "period": per,
                "new_songs": int(len(g)),
                "clusters": {str(int(c)): int(v) for c, v in counts.items()},
                "top_genre": p.gname(genre.index[0]) if len(genre) else None,
            })
        out["timeline"] = {"by": "month" if by_month else "year", "periods": timeline}

    # ---- lists worth acting on -------------------------------------------------------------
    lists: Dict[str, Any] = {}
    last = [t.get("last_played") for t in tracks]
    if plays is not None and plays.sum() > 0 and any(last):
        newest = max(d for d in last if d)
        cutoff = f"{int(newest[:4]) - 1}{newest[4:]}"  # a year before the newest play
        loved = plays >= max(np.quantile(plays[plays > 0], 0.8), 3) if (plays > 0).any() else plays > 0
        idx = [i for i in np.argsort(-plays) if loved[i] and last[i] and last[i] < cutoff][:15]
        lists["rediscover"] = [{"id": int(i), "plays": int(plays[i]), "last_played": last[i]} for i in idx]
    if skips is not None and plays is not None and skips.sum() > 0:
        rate = skips / np.maximum(plays + skips, 1)
        idx = [i for i in np.argsort(-skips) if skips[i] >= 3 and rate[i] >= 0.5][:15]
        lists["skipped"] = [{"id": int(i), "skips": int(skips[i]), "plays": int(plays[i]),
                             "skip_rate": round(float(rate[i]), 2)} for i in idx]
    if n >= 20 and nn_dist.size:
        loneliness = nn_dist.mean(axis=1)
        idx = np.argsort(-loneliness)[:12]
        lists["unusual"] = [{"id": int(i)} for i in idx]
    if plays is not None and overview.get("never_played"):
        never = np.where(plays == 0)[0]
        if p.engagement is not None and cols["liked"]:  # liked but never played comes first
            never = never[np.argsort(-p.engagement[never], kind="stable")]
        lists["never_played"] = [{"id": int(i)} for i in never[:15]]
    if lists:
        out["lists"] = lists
    return out
