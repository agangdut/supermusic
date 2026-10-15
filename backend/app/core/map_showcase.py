"""What the Shared maps page shows for each map: a picture of it and a few stats worth
showing off. Both are worked out once, when a map is shared (or the first time an older
share is listed), and saved next to it.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any, Dict, List

import numpy as np

# The same colours the 3D view gives clusters (frontend/components/map/colors.js)
CLUSTER_COLORS = ["#a78bfa", "#38bdf8", "#f472b6", "#34d399", "#fbbf24",
                  "#fb7185", "#22d3ee", "#c084fc", "#a3e635", "#f97316"]
HIDDEN_COLOR = "#f0abfc"
BACKGROUND = "#05070f"


def color_for(cluster: int) -> str:
    return CLUSTER_COLORS[int(cluster or 0) % len(CLUSTER_COLORS)]


def _name(c: dict) -> str:
    return c.get("name") or (c.get("label") or "Cluster").split(" · ")[0]


def _top(values: List[str], n: int) -> List[Dict[str, Any]]:
    return [{"name": v, "songs": k} for v, k in Counter(v for v in values if v).most_common(n)]


def showcase(m: Dict[str, Any]) -> Dict[str, Any]:
    """Headline numbers and lists for a map's card."""
    tracks = m.get("tracks") or []
    clusters = sorted(m.get("clusters") or [], key=lambda c: -c.get("size", 0))
    out: Dict[str, Any] = {
        "songs": len(tracks),
        "artists": len({(t.get("artist") or "").lower() for t in tracks if t.get("artist")}),
        "clusters": len(clusters),
        "hidden_links": len(m.get("hidden_connections") or []),
    }
    out["galaxies"] = [{"id": c.get("id"), "name": _name(c), "label": c.get("label"), "size": c.get("size"),
                        "color": color_for(c.get("id", 0))} for c in clusters[:5]]
    first_genre = [(t.get("genre") or "").split(",")[0].strip() for t in tracks]
    out["top_genres"] = _top(first_genre, 3)
    out["top_artists"] = _top([t.get("artist") for t in tracks], 3)
    keys = Counter(t.get("key") for t in tracks if t.get("key"))
    if keys:
        out["top_key"] = keys.most_common(1)[0][0]
    bpms = [t["bpm"] for t in tracks if isinstance(t.get("bpm"), (int, float)) and 40 <= t["bpm"] <= 220]
    if bpms:
        out["median_bpm"] = round(median(bpms))
    years = [t["year"] for t in tracks if isinstance(t.get("year"), int)]
    if years:
        decades = Counter(y // 10 * 10 for y in years)
        out["top_decade"] = f"{decades.most_common(1)[0][0]}s"
        out["years"] = [min(years), max(years)]
    plays = [t["plays"] for t in tracks if isinstance(t.get("plays"), (int, float))]
    if plays and sum(plays) > 0:
        out["plays"] = int(sum(plays))
        top = max(tracks, key=lambda t: t.get("plays") or 0)
        out["most_played"] = {"title": top.get("title"), "artist": top.get("artist"), "plays": int(top.get("plays") or 0)}
    loved = [c for c in clusters if isinstance(c.get("lift"), (int, float))]
    if loved:
        c = max(loved, key=lambda c: c["lift"])
        out["most_loved"] = {"name": _name(c), "label": c.get("label"), "lift": c["lift"],
                             "listening_share": c.get("listening_share")}
    hidden = m.get("hidden_connections") or []
    if hidden:
        by_id = {t.get("id"): t for t in tracks}
        h = max(hidden, key=lambda h: h.get("strength") or 0)
        a, b = by_id.get(h.get("source")), by_id.get(h.get("target"))
        if a and b:
            out["best_link"] = {"a": a.get("title"), "a_artist": a.get("artist"),
                                "b": b.get("title"), "b_artist": b.get("artist"),
                                "why": (h.get("reasons") or [None])[0]}
    return out


def render_picture(m: Dict[str, Any], path: Path, width: int = 1200, height: int = 675) -> None:
    """A glowing front view of the map, like the 3D view's opening shot, as a PNG."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    tracks = m.get("tracks") or []
    xy = np.array([[t.get("x") or 0.0, t.get("y") or 0.0] for t in tracks], dtype=float)
    colors = [color_for(t.get("cluster", 0)) for t in tracks]
    eng = np.array([t.get("engagement") or 0.0 for t in tracks], dtype=float)

    dpi = 100
    fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi, facecolor=BACKGROUND)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BACKGROUND)
    ax.axis("off")

    # A soft violet haze in the middle, like the page's background
    yy, xx = np.mgrid[-1:1:200j, -1.78:1.78:356j]
    haze = np.exp(-(xx ** 2 / 1.6 + yy ** 2 / 0.9))
    ax.imshow(np.dstack([np.full_like(haze, 0.10), np.full_like(haze, 0.08), np.full_like(haze, 0.25), haze * 0.55]),
              extent=(0, 1, 0, 1), transform=ax.transAxes, zorder=0)

    if len(xy):
        lo, hi = np.percentile(xy, 1, axis=0), np.percentile(xy, 99, axis=0)
        span = np.maximum(hi - lo, 1e-6)
        pad = span * 0.12
        # Keep the map's proportions inside a 16:9 frame
        w, h = span[0] + 2 * pad[0], span[1] + 2 * pad[1]
        aspect = width / height
        if w / h < aspect:
            w = h * aspect
        else:
            h = w / aspect
        cx, cy = (lo + hi) / 2
        ax.set_xlim(cx - w / 2, cx + w / 2)
        ax.set_ylim(cy - h / 2, cy + h / 2)

        # Each cluster's own web of links, faint; hidden links in pink on top
        segs, seg_colors, hidden = [], [], []
        index = {t.get("id"): i for i, t in enumerate(tracks)}
        for e in (m.get("edges") or [])[:40000]:
            a, b = index.get(e.get("source")), index.get(e.get("target"))
            if a is None or b is None:
                continue
            if e.get("kind") == "hidden":
                hidden.append([xy[a], xy[b]])
            elif not e.get("bridge"):
                segs.append([xy[a], xy[b]])
                seg_colors.append(colors[a])
        if segs:
            ax.add_collection(LineCollection(segs, colors=seg_colors, linewidths=0.5,
                                             alpha=0.18 if len(tracks) < 2500 else 0.05, zorder=1))
        if hidden:
            ax.add_collection(LineCollection(hidden, colors=HIDDEN_COLOR, linewidths=0.9, alpha=0.55, zorder=2))

        # Stars: a wide faint glow, then a bright core; songs played more are bigger
        n = len(tracks)
        base = 26 if n < 300 else 12 if n < 2500 else 3
        size = base * (1 + 2.5 * np.sqrt(np.clip(eng, 0, 1)))
        for scale, alpha in ((9, 0.05), (3.5, 0.14), (1, 0.9)):
            ax.scatter(xy[:, 0], xy[:, 1], s=size * scale, c=colors, alpha=alpha, linewidths=0, zorder=3)

        # Name the biggest galaxies above their stars
        clusters = sorted(m.get("clusters") or [], key=lambda c: -c.get("size", 0))[:6]
        cl = np.array([t.get("cluster", 0) for t in tracks])
        for c in clusters:
            members = xy[cl == c.get("id")]
            if not len(members):
                continue
            x, y = members[:, 0].mean(), np.percentile(members[:, 1], 95)
            ax.text(x, y + h * 0.025, _name(c), color=color_for(c.get("id", 0)), ha="center", va="bottom",
                    fontsize=15, fontweight="bold", alpha=0.95, zorder=4)

    fig.savefig(path, dpi=dpi, facecolor=BACKGROUND)
    plt.close(fig)



def render_card(meta: Dict[str, Any], picture: Path, path: Path, width: int = 1200, height: int = 630) -> None:
    """A Wrapped-style card for chats and socials: the map on the right, the headline facts on the left.
    1200x630 is the size link previews (Open Graph) expect."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, FancyBboxPatch

    s = meta.get("showcase") or {}
    dpi = 100
    fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi, facecolor=BACKGROUND)

    # The map picture fills the right side, fading into the background on its left edge
    ax_img = fig.add_axes([0.38, 0, 0.62, 1])
    ax_img.axis("off")
    if picture.is_file():
        img = plt.imread(picture)[..., :3].astype(float)
        if img.max() > 1:
            img /= 255
        h, w = img.shape[:2]
        cw = min(w, int(h * (0.62 * width) / height))
        x0 = (w - cw) // 2
        img = img[:, x0:x0 + cw]
        bg = np.array([5, 7, 15]) / 255
        fade = np.clip(np.linspace(0, 1, img.shape[1]) / 0.35, 0, 1) ** 1.5
        img = img * fade[None, :, None] + bg[None, None, :] * (1 - fade[None, :, None])
        ax_img.imshow(img, aspect="auto")

    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)

    ax.text(56, height - 64, "Super", color="#e5e7eb", fontsize=20, fontweight="bold", va="center")
    ax.text(140, height - 64, "Music", color="#c084fc", fontsize=20, fontweight="bold", va="center")
    title = str(meta.get("title") or "My music map")
    if len(title) > 26:
        title = title[:25] + "…"
    ax.text(56, height - 150, title, color="white", fontsize=36, fontweight="bold", va="center")
    by = meta.get("by")
    ax.text(56, height - 200, f"by {by}" if by else "a SuperMusic map", color="#9ca3af", fontsize=17, va="center")

    stats = [(s.get("songs") or meta.get("songs") or 0, "songs"), (s.get("artists") or 0, "artists"),
             (s.get("clusters") or 0, "galaxies")]
    for i, (v, label) in enumerate(stats):
        x = 56 + i * 150
        txt = f"{v / 1000:.1f}k" if v >= 10000 else f"{v:,}"
        ax.text(x, height - 280, txt, color="white", fontsize=30, fontweight="bold", va="center")
        ax.text(x, height - 318, label.upper(), color="#6b7280", fontsize=11, va="center")

    y = height - 380
    renderer = fig.canvas.get_renderer()
    for g in (s.get("galaxies") or [])[:3]:
        color = g.get("color") or "#a78bfa"
        ax.add_patch(Circle((66, y), 7, color=color))
        ax.add_patch(Circle((66, y), 14, color=color, alpha=0.18))
        name = ax.text(88, y, g.get("name") or "", color="white", fontsize=17, fontweight="bold", va="center")
        right = ax.transData.inverted().transform((name.get_window_extent(renderer=renderer).x1, 0))[0]
        ax.text(right + 12, y, (g.get("label") or "").split(" · ")[0], color="#9ca3af", fontsize=14, va="center")
        y -= 44

    line = None
    if s.get("best_link"):
        b = s["best_link"]
        line = f"Hidden link: {b['a']} ↔ {b['b']}"
    elif s.get("most_played"):
        line = f"Most played: {s['most_played']['title']}"
    if line:
        if len(line) > 52:
            line = line[:51] + "…"
        ax.add_patch(FancyBboxPatch((50, 40), 470, 46, boxstyle="round,pad=0,rounding_size=12",
                                    facecolor="#f0abfc", alpha=0.10, edgecolor="#f0abfc", linewidth=0.8))
        ax.text(66, 63, line, color="#f5d0fe", fontsize=13, va="center")

    fig.savefig(path, dpi=dpi, facecolor=BACKGROUND)
    plt.close(fig)
