"""
Music map: turn a track list into a 3D "taste map".

Given a CSV of tracks (any mix of title/artist/genre/key/bpm/audio features
and, optionally, listening data like play_count or rating) this module:

1. builds a feature vector per track, with musical keys placed on the
   Camelot wheel so harmonically compatible keys sit close together,
2. projects the tracks into 3D (UMAP, or PCA for tiny libraries),
3. groups them into clusters and scores each cluster's "signal": how much
   more the listener plays it than its size alone would predict,
4. links each track to its nearest neighbours and flags "hidden
   connections", i.e. close neighbours that live in different clusters,
5. recommends under-played tracks that sit closest to the listener's taste.

Everything works from CSV columns alone; no audio is needed.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from app.core.genres import summarise as summarise_genres

# ---------------------------------------------------------------------------
# Column detection
# ---------------------------------------------------------------------------

ALIASES: Dict[str, Sequence[str]] = {
    "title": ("title", "name", "track", "track_name", "song", "song_name"),
    "artist": ("artist", "artists", "artist_name", "performer"),
    "album": ("album", "album_name", "release"),
    "genre": ("genre", "genres", "style", "tags"),
    "key": ("key", "musical_key", "camelot", "key_name"),
    "mode": ("mode",),
    "bpm": ("bpm", "tempo"),
    "year": ("year", "release_year"),
    "duration": ("duration_sec", "duration", "duration_s", "length", "duration_ms"),
    # listening signal
    "plays": ("play_count", "plays", "playcount", "listens", "listen_count", "streams", "scrobbles", "minutes_played"),
    "rating": ("rating", "stars", "score"),
    "liked": ("liked", "loved", "favorite", "favourite", "saved", "is_liked"),
    "skips": ("skip_count", "skips", "skipped"),
}

# Audio descriptors we use as-is when present (Spotify-style, 0..1 mostly)
AUDIO_FEATURES = (
    "energy", "danceability", "valence", "acousticness", "instrumentalness",
    "speechiness", "liveness", "loudness", "brightness",
)

# Columns that never become features (identifiers, links, our own output)
IGNORED = {"track_id", "id", "youtube_url", "url", "local_path", "path", "x", "y", "z", "isrc", "uri"}


def _find(df: pd.DataFrame, field_name: str) -> Optional[str]:
    lower = {c.lower().strip(): c for c in df.columns}
    for alias in ALIASES[field_name]:
        if alias in lower:
            return lower[alias]
    return None


# ---------------------------------------------------------------------------
# Musical keys
# ---------------------------------------------------------------------------

_PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
# Camelot number for each pitch class: major (B) and minor (A) rings
_CAMELOT_MAJOR = {0: 8, 7: 9, 2: 10, 9: 11, 4: 12, 11: 1, 6: 2, 1: 3, 8: 4, 3: 5, 10: 6, 5: 7}
_CAMELOT_MINOR = {9: 8, 4: 9, 11: 10, 6: 11, 1: 12, 8: 1, 3: 2, 10: 3, 5: 4, 0: 5, 7: 6, 2: 7}
_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


@dataclass(frozen=True)
class Key:
    pitch: int        # 0..11, C = 0
    minor: bool

    @property
    def camelot(self) -> str:
        n = (_CAMELOT_MINOR if self.minor else _CAMELOT_MAJOR)[self.pitch]
        return f"{n}{'A' if self.minor else 'B'}"

    @property
    def camelot_number(self) -> int:
        return int(self.camelot[:-1])

    @property
    def name(self) -> str:
        return f"{_NAMES[self.pitch]}{'m' if self.minor else ''}"

    @property
    def long_name(self) -> str:
        return f"{_NAMES[self.pitch]} {'minor' if self.minor else 'major'}"


def parse_key(value: Any, mode: Any = None) -> Optional[Key]:
    """Parse 'Am', 'C#m', 'F# minor', 'Bb', '8A' (Camelot), or 0..11 + mode."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    s = str(value).strip()
    if not s:
        return None

    # Spotify style: integer pitch class plus a separate mode column (1 = major)
    if re.fullmatch(r"-?\d+(\.0)?", s):
        pc = int(float(s))
        if pc < 0 or pc > 11:
            return None
        minor = False
        if mode is not None and not (isinstance(mode, float) and math.isnan(mode)):
            minor = str(mode).strip().lower() in {"0", "0.0", "minor", "min", "m"}
        return Key(pc, minor)

    # Camelot: 1A..12B
    m = re.fullmatch(r"(1[0-2]|[1-9])\s*([AaBb])", s)
    if m:
        num, ring = int(m.group(1)), m.group(2).upper()
        table = _CAMELOT_MINOR if ring == "A" else _CAMELOT_MAJOR
        for pc, n in table.items():
            if n == num:
                return Key(pc, ring == "A")

    # Note name + optional accidental + optional quality
    m = re.fullmatch(r"([A-Ga-g])\s*([#♯b♭]?)\s*(.*)", s)
    if not m:
        return None
    pc = _PITCH[m.group(1).upper()]
    acc = m.group(2)
    if acc in ("#", "♯"):
        pc += 1
    elif acc in ("b", "♭"):
        pc -= 1
    quality = m.group(3).strip().lower()
    minor = quality in {"m", "min", "minor", "-"} or quality.startswith("min")
    if not minor and quality and quality not in {"maj", "major"}:
        return None
    return Key(pc % 12, minor)


def harmonic_match(a: Key, b: Key) -> Optional[str]:
    """Why two keys mix well (DJ 'harmonic mixing'), or None."""
    if a == b:
        return f"both in {a.long_name}"
    na, nb = a.camelot_number, b.camelot_number
    if na == nb:
        return f"relative keys ({a.name} / {b.name})"
    if a.minor == b.minor and (abs(na - nb) in (1, 11)):
        return f"neighbouring keys on the Camelot wheel ({a.camelot} → {b.camelot})"
    return None


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class MapOptions:
    neighbors: int = 4
    clusters: Optional[int] = None
    # How much each aspect shapes the map (0 = ignore, 1 = normal, 2 = strong)
    weights: Dict[str, float] = field(default_factory=lambda: {
        "key": 1.0, "tempo": 1.0, "genre": 1.0, "mood": 1.0, "artist": 0.5, "era": 0.5,
    })


# ---------------------------------------------------------------------------
# Feature building
# ---------------------------------------------------------------------------

def _zscore(col: np.ndarray) -> np.ndarray:
    col = col.astype(float)
    mean = np.nanmean(col) if np.isfinite(col).any() else 0.0
    col = np.where(np.isfinite(col), col, mean)
    std = col.std()
    return (col - mean) / std if std > 1e-9 else np.zeros_like(col)


def _split_tags(v: Any) -> List[str]:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return []
    # Not "/": names like "Hip-Hop/Rap" (Apple) or "Rap/Hip Hop" (Deezer) are one genre, not two
    return [t.strip().lower() for t in re.split(r"[;,|]", str(v)) if t.strip()]


def _broad_genres(tags: List[str]) -> List[str]:
    """Fine-grained tags -> at most two broad genres. Earlier tags count a little more,
    since Exportify lists the main artist's genres before any featured artist's."""
    return summarise_genres([(t, 1.0 / (1 + 0.15 * i)) for i, t in enumerate(tags)])


def _one_hot(values: List[List[str]], min_count: int = 1) -> Tuple[np.ndarray, List[str]]:
    counts: Dict[str, int] = {}
    for tags in values:
        for t in set(tags):
            counts[t] = counts.get(t, 0) + 1
    vocab = sorted(t for t, c in counts.items() if c >= min_count)
    idx = {t: i for i, t in enumerate(vocab)}
    mat = np.zeros((len(values), len(vocab)))
    for r, tags in enumerate(values):
        for t in tags:
            if t in idx:
                mat[r, idx[t]] = 1.0
    # Normalise rows so multi-genre tracks don't outweigh single-genre ones
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    return np.divide(mat, norms, out=np.zeros_like(mat), where=norms > 0), vocab


def _engagement(df: pd.DataFrame, cols: Dict[str, Optional[str]]) -> Optional[np.ndarray]:
    """One 0..1 'how much do I love this' score per track, or None."""
    parts: List[np.ndarray] = []
    if cols["plays"]:
        plays = pd.to_numeric(df[cols["plays"]], errors="coerce").fillna(0).clip(lower=0).to_numpy()
        lp = np.log1p(plays)
        parts.append(lp / lp.max() if lp.max() > 0 else lp)
    if cols["rating"]:
        r = pd.to_numeric(df[cols["rating"]], errors="coerce")
        lo, hi = r.min(), r.max()
        if pd.notna(lo) and hi > lo:
            parts.append(((r - lo) / (hi - lo)).fillna(0).to_numpy())
    if cols["liked"]:
        liked = df[cols["liked"]].astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y", "1.0", "♥", "x"})
        parts.append(liked.to_numpy(dtype=float))
    if not parts:
        return None
    score = np.mean(parts, axis=0)
    if cols["skips"]:
        skips = pd.to_numeric(df[cols["skips"]], errors="coerce").fillna(0).clip(lower=0).to_numpy()
        ls = np.log1p(skips)
        if ls.max() > 0:
            score = score * (1 - 0.5 * ls / ls.max())
    return score


@dataclass
class _Prepared:
    df: pd.DataFrame
    cols: Dict[str, Optional[str]]
    keys: List[Optional[Key]]
    bpm: Optional[np.ndarray]
    genres: List[List[str]]  # broad genres (lower case), at most two per track
    genre_names: Dict[str, str]
    styles: List[List[str]]  # the file's own detailed tags
    style_names: Dict[str, str]
    artists: List[str]
    musical: Optional[np.ndarray]
    features: np.ndarray
    feature_groups: List[str]
    mood_cols: List[str]
    engagement: Optional[np.ndarray]
    _lib_genres: Optional[Dict[str, float]] = None  # filled in on first use by _distinctive_style
    _lib_styles: Optional[Dict[str, float]] = None

    def gname(self, g: str) -> str:
        return self.genre_names.get(g, g.title())


def _prepare(df: pd.DataFrame, opts: MapOptions) -> _Prepared:
    cols = {name: _find(df, name) for name in ALIASES}
    w = {**MapOptions().weights, **(opts.weights or {})}
    blocks: List[np.ndarray] = []
    groups: List[str] = []

    def add(block: np.ndarray, weight: float, group: str) -> None:
        if weight <= 0 or block.size == 0 or block.shape[1] == 0:
            return
        blocks.append(block * weight)
        groups.append(group)

    # Key: angle on the Camelot wheel (so 8A sits next to 7A and 9A), plus ring
    mode_col = cols["mode"]
    keys = [
        parse_key(df[cols["key"]].iloc[i], df[mode_col].iloc[i] if mode_col else None) if cols["key"] else None
        for i in range(len(df))
    ]
    kb = np.zeros((len(df), 3))
    if any(keys):
        for i, k in enumerate(keys):
            if k:
                ang = 2 * math.pi * (k.camelot_number - 1) / 12
                kb[i] = [math.cos(ang), math.sin(ang), 0.6 if k.minor else -0.6]
        add(kb, 1.4 * w["key"], "key")

    # Tempo: log scale, so 90 vs 100 matters as much as 135 vs 150
    bpm = None
    if cols["bpm"]:
        bpm = pd.to_numeric(df[cols["bpm"]], errors="coerce").to_numpy(dtype=float)
        if np.isfinite(bpm).any():
            add(_zscore(np.log2(np.where(bpm > 0, bpm, np.nan)))[:, None], 1.2 * w["tempo"], "tempo")

    # Genre columns from Spotify hold many fine-grained tags per song ("toronto rap, pop rap, canadian pop").
    # Counted as-is, a tag that many artists share ("rap", "pop") ends up naming every cluster, and the
    # fragments are too sparse to group songs. So each song also gets one or two broad genres (Hip-Hop,
    # Pop, R&B, ...): these drive the grouping and every label; the detailed tags only fine-tune.
    styles = [_split_tags(v) for v in df[cols["genre"]]] if cols["genre"] else [[] for _ in range(len(df))]
    style_names: Dict[str, str] = {}
    if cols["genre"]:
        for v in df[cols["genre"]]:
            for t in re.split(r"[;,|]", str(v)) if pd.notna(v) else []:
                style_names.setdefault(t.strip().lower(), t.strip())
    genres: List[List[str]] = []
    genre_names: Dict[str, str] = {}
    for tags in styles:
        broad = _broad_genres(tags)
        if not broad and tags:  # nothing recognisable: keep the file's own first tag
            broad = [style_names.get(tags[0], tags[0])]
        genres.append([g.lower() for g in broad])
        for g in broad:
            genre_names.setdefault(g.lower(), g)
    if any(genres):
        g, _ = _one_hot(genres)
        add(g, 1.6 * w["genre"], "genre")
    if any(set(t) != set(g) for t, g in zip(styles, genres)):
        st, _ = _one_hot(styles)
        add(st, 0.6 * w["genre"], "style")

    lower = {c.lower(): c for c in df.columns}
    mood_cols = [lower[f] for f in AUDIO_FEATURES if f in lower]
    if mood_cols:
        mood = np.column_stack([_zscore(pd.to_numeric(df[c], errors="coerce").to_numpy()) for c in mood_cols])
        add(mood / math.sqrt(len(mood_cols)) * 1.6, w["mood"], "mood")

    artists = [str(v).strip() if pd.notna(v) else "" for v in df[cols["artist"]]] if cols["artist"] else [""] * len(df)
    if any(artists):
        a, vocab = _one_hot([[x.lower()] if x else [] for x in artists], min_count=2)
        if vocab:
            add(a, 1.0 * w["artist"], "artist")

    if cols["year"]:
        yr = pd.to_numeric(df[cols["year"]], errors="coerce").to_numpy(dtype=float)
        if np.isfinite(yr).any():
            add(_zscore(yr)[:, None], 0.8 * w["era"], "era")

    # Fall back to any other numeric columns if nothing above matched
    if not blocks:
        known = {c for c in cols.values() if c}
        nums = [c for c in df.columns if c not in known and c.lower() not in IGNORED
                and pd.api.types.is_numeric_dtype(df[c])]
        if nums:
            add(np.column_stack([_zscore(df[c].to_numpy()) for c in nums]), 1.0, "numeric")

    musical_blocks: List[np.ndarray] = []
    if any(keys):
        musical_blocks.append(kb * 1.4)
    if bpm is not None and np.isfinite(bpm).any():
        # Fold tempo by octaves so 87 BPM sits on top of 174 BPM (half/double time)
        frac = np.log2(np.where(bpm > 0, bpm, np.nan)) % 1.0
        ang = 2 * np.pi * np.where(np.isfinite(frac), frac, 0)
        tb = np.column_stack([np.cos(ang), np.sin(ang)]) * 1.2
        tb[~np.isfinite(frac)] = 0
        musical_blocks.append(tb)
    if mood_cols:
        musical_blocks.append(mood / math.sqrt(len(mood_cols)))
    musical = np.hstack(musical_blocks) if len(musical_blocks) >= 2 else None

    if not blocks:
        raise ValueError(
            "Couldn't find anything to compare tracks on. Add columns such as "
            "genre, key, bpm, energy or valence."
        )

    return _Prepared(
        df=df, cols=cols, keys=keys, bpm=bpm, genres=genres, genre_names=genre_names,
        styles=styles, style_names=style_names,
        artists=artists, musical=musical,
        features=np.hstack(blocks), feature_groups=groups, mood_cols=mood_cols,
        engagement=_engagement(df, cols),
    )


# ---------------------------------------------------------------------------
# Layout and clustering
# ---------------------------------------------------------------------------

def _embed_3d(x: np.ndarray, n_neighbors: int = 15) -> Tuple[np.ndarray, str]:
    n = x.shape[0]
    if n >= 12:
        import umap  # heavy import, keep it lazy

        reducer = umap.UMAP(
            n_components=3, n_neighbors=max(2, min(n_neighbors, n - 1)),
            min_dist=0.25, metric="euclidean", random_state=42,
        )
        emb = reducer.fit_transform(x)
        method = "umap"
    else:
        from sklearn.decomposition import PCA

        k = min(3, n, x.shape[1])
        emb = PCA(n_components=k).fit_transform(x) if k > 0 else np.zeros((n, 0))
        if emb.shape[1] < 3:
            emb = np.hstack([emb, np.zeros((n, 3 - emb.shape[1]))])
        method = "pca"
    emb = emb - emb.mean(axis=0)
    scale = np.abs(emb).max() or 1.0
    return emb / scale * 100.0, method


def _spread_clusters(emb: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """UMAP packs each cluster into a tight knot; open them up so every track is visible."""
    out = emb.copy()
    for c in set(labels.tolist()):
        idx = np.where(labels == c)[0]
        if len(idx) < 2:
            continue
        centre = emb[idx].mean(axis=0)
        offsets = emb[idx] - centre
        radius = np.linalg.norm(offsets, axis=1).mean()
        target = 8 + 2.4 * math.sqrt(len(idx))
        if radius > 1e-6:
            out[idx] = centre + offsets * (target / radius)
    return _separate_clusters(out, labels)


def _separate_clusters(emb: np.ndarray, labels: np.ndarray, gap: float = 10.0) -> np.ndarray:
    """Nudge overlapping clusters apart so each one reads as its own island."""
    ids = sorted(set(labels.tolist()))
    if len(ids) < 2:
        return emb
    idx = [np.where(labels == c)[0] for c in ids]
    centres = np.array([emb[i].mean(axis=0) for i in idx])
    radii = np.array([np.linalg.norm(emb[i] - emb[i].mean(axis=0), axis=1).mean() * 1.6 if len(i) > 1 else 4.0 for i in idx])
    moved = centres.copy()
    for _ in range(200):
        shifted = False
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                d = moved[b] - moved[a]
                dist = float(np.linalg.norm(d))
                need = radii[a] + radii[b] + gap
                if dist >= need:
                    continue
                direction = d / dist if dist > 1e-6 else np.random.default_rng(a * 31 + b).normal(size=3)
                direction /= np.linalg.norm(direction)
                push = (need - dist) / 2 * direction
                moved[a] -= push
                moved[b] += push
                shifted = True
        if not shifted:
            break
    out = emb.copy()
    for i, before, after in zip(idx, centres, moved):
        out[i] += after - before
    out -= out.mean(axis=0)
    return out


def _cluster(emb: np.ndarray, k: Optional[int]) -> np.ndarray:
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    n = emb.shape[0]
    if n < 6:
        return np.zeros(n, dtype=int)
    if k:
        k = max(1, min(k, n - 1))
        return KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(emb)
    # Real libraries blur together, so silhouette alone tends to pick 2 huge
    # clusters. Ask for roughly one cluster per ~30 tracks at least.
    k_max = min(10, max(3, n // 5))
    k_min = min(k_max, max(2, round(math.sqrt(n) / 2.5)))
    best, best_score = None, -1.0
    for k in range(k_min, k_max + 1):
        labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(emb)
        score = silhouette_score(emb, labels)
        if score > best_score:
            best, best_score = labels, score
    return best if best is not None else np.zeros(n, dtype=int)


# ---------------------------------------------------------------------------
# Describing things in words
# ---------------------------------------------------------------------------

def _share(values: List[Any], weights: Optional[np.ndarray] = None) -> List[Tuple[Any, float]]:
    totals: Dict[Any, float] = {}
    for i, v in enumerate(values):
        if v in (None, ""):
            continue
        totals[v] = totals.get(v, 0.0) + (float(weights[i]) if weights is not None else 1.0)
    s = sum(totals.values()) or 1.0
    return sorted(((v, t / s) for v, t in totals.items()), key=lambda kv: -kv[1])


def _bpm_range(bpms: np.ndarray) -> Optional[Tuple[int, int]]:
    b = bpms[np.isfinite(bpms)]
    if b.size == 0:
        return None
    lo, hi = np.percentile(b, [20, 80])
    return int(round(lo)), int(round(hi))


def _bpm_bucket(bpm: float) -> Optional[str]:
    if not np.isfinite(bpm) or bpm <= 0:
        return None
    lo = int(bpm // 10 * 10)
    return f"{lo}–{lo + 9} BPM"


# Tags too broad to tell one part of a library from another
_GENERIC_STYLES = {"rap", "hip hop", "hip-hop", "hiphop", "pop", "rock", "r&b", "rnb", "soul", "electronic", "dance"}


def _style_fractions(p: _Prepared, idx) -> Dict[str, float]:
    """Share of the given tracks that carry each detailed tag."""
    counts: Dict[str, int] = {}
    for i in idx:
        for t in set(p.styles[i]):
            counts[t] = counts.get(t, 0) + 1
    return {t: c / max(len(idx), 1) for t, c in counts.items()}


def _distinctive_style(p: _Prepared, idx: np.ndarray, top_genre: str) -> Optional[str]:
    """When most of the library shares one broad genre (say Hip-Hop), naming every cluster
    "Hip-Hop" says nothing. Name it after the detailed tag that sets it apart instead
    ("West Coast Hip Hop", "Melodic Rap", "Trap Soul")."""
    if p._lib_genres is None:
        p._lib_genres = dict(_share([t for gs in p.genres for t in gs]))
        p._lib_styles = _style_fractions(p, range(len(p.styles)))
    if p._lib_genres.get(top_genre, 0) < 0.5:
        return None  # the broad genre already tells clusters apart
    here = _style_fractions(p, idx)
    best, best_score = None, 0.0
    for t, f in here.items():
        if t in _GENERIC_STYLES or t == top_genre or f < 0.25:
            continue
        lift = f / max(p._lib_styles.get(t, f), 1e-9)
        score = f * lift
        if (lift >= 1.2 or f >= 0.6) and score > best_score:
            best, best_score = t, score
    if not best:
        return None
    name = p.style_names.get(best, best)
    return name if any(c.isupper() for c in name) else name.title().replace("Hip Hop", "Hip-Hop")


def _cluster_label(p: _Prepared, idx: np.ndarray) -> Tuple[str, Dict[str, Any]]:
    parts: List[str] = []
    info: Dict[str, Any] = {}

    g = _share([t for i in idx for t in p.genres[i]])
    if g:
        info["top_genres"] = [{"name": p.gname(n), "share": round(s, 2)} for n, s in g[:3]]
        if g[0][1] < 0.35:  # no genre leads; naming one would mislabel most of the cluster
            label = "Mix of " + ", ".join(p.gname(n) for n, _ in g[:3])
        else:
            label = " / ".join(p.gname(n) for n, s in g[:2] if s >= 0.25)
        style = _distinctive_style(p, idx, g[0][0]) if g[0][1] >= 0.5 else None
        if style:
            info["style"] = style
            label = style
        parts.append(label)

    ks = _share([p.keys[i].camelot for i in idx if p.keys[i]])
    if ks:
        by_cam = {p.keys[i].camelot: p.keys[i] for i in idx if p.keys[i]}
        info["top_keys"] = [{"camelot": c, "name": by_cam[c].name, "share": round(s, 2)} for c, s in ks[:3]]
        if ks[0][1] >= 0.35:
            parts.append(by_cam[ks[0][0]].long_name)

    if p.bpm is not None:
        r = _bpm_range(p.bpm[idx])
        if r:
            info["bpm_range"] = list(r)
            parts.append(f"{r[0]}–{r[1]} BPM" if r[0] != r[1] else f"{r[0]} BPM")

    if p.mood_cols:
        df = p.df.iloc[idx]
        moods = []
        for col, hi_word, lo_word in (("energy", "high-energy", "mellow"), ("valence", "upbeat", "moody"),
                                       ("acousticness", "acoustic", None), ("danceability", "danceable", None)):
            c = next((m for m in p.mood_cols if m.lower() == col), None)
            if c is None:
                continue
            cluster_mean = pd.to_numeric(df[c], errors="coerce").mean()
            all_mean = pd.to_numeric(p.df[c], errors="coerce").mean()
            all_std = pd.to_numeric(p.df[c], errors="coerce").std() or 1
            z = (cluster_mean - all_mean) / all_std
            if z > 0.6 and hi_word:
                moods.append(hi_word)
            elif z < -0.6 and lo_word:
                moods.append(lo_word)
        if moods:
            info["mood"] = moods[:2]
            parts.append(", ".join(moods[:2]))

    return " · ".join(parts) or f"Group of {len(idx)}", info


def _pair_reasons(p: _Prepared, i: int, j: int) -> List[str]:
    reasons: List[str] = []
    ki, kj = p.keys[i], p.keys[j]
    if ki and kj:
        h = harmonic_match(ki, kj)
        if h:
            reasons.append(h)
    if p.bpm is not None and np.isfinite(p.bpm[i]) and np.isfinite(p.bpm[j]) and p.bpm[i] > 0:
        a, b = p.bpm[i], p.bpm[j]
        if abs(a - b) / max(a, b) <= 0.04:
            reasons.append(f"same tempo (~{int(round((a + b) / 2))} BPM)")
        elif abs(a - 2 * b) / a <= 0.04 or abs(b - 2 * a) / b <= 0.04:
            reasons.append(f"half/double time ({int(a)} ↔ {int(b)} BPM)")
    shared = sorted(set(p.genres[i]) & set(p.genres[j]))
    if shared:
        reasons.append("both " + " / ".join(p.gname(s) for s in shared[:2]))
    if p.artists[i] and p.artists[i].lower() == p.artists[j].lower():
        reasons.append(f"same artist ({p.artists[i]})")
    if p.mood_cols:
        close = []
        for c in p.mood_cols:
            col = pd.to_numeric(p.df[c], errors="coerce")
            std = col.std() or 1
            a, b = col.iloc[i], col.iloc[j]
            if pd.notna(a) and pd.notna(b) and abs(a - b) <= 0.25 * std:
                close.append(c.lower())
        if len(close) >= 2:
            reasons.append("similar " + " and ".join(close[:2]))
    return reasons


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

# Seconds to draw a map of n tracks ≈ BUILD_COST * n^1.5 (UMAP dominates), measured on a
# 4-core CPU: 500 tracks 2.4 s, 1,500 tracks 10.8 s, 3,000 tracks 29.6 s. Each finished build
# re-calibrates it, so estimates follow the machine this actually runs on.
_build_cost = [1.9e-4]
_umap_ready = [False]
UMAP_FIRST_RUN_S = 15.0  # UMAP compiles itself the first time it runs


def estimate_build_seconds(n: int) -> float:
    """How long build_map should take for n tracks on this machine."""
    est = 0.5 + _build_cost[0] * max(n, 1) ** 1.5
    if n >= 12 and not _umap_ready[0]:
        est += UMAP_FIRST_RUN_S
    return est


def build_map(df: pd.DataFrame, opts: Optional[MapOptions] = None,
              progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """`progress`, if given, is called with the name of each step as it starts."""
    import time

    opts = opts or MapOptions()
    step = progress or (lambda _s: None)
    df = df.dropna(how="all").reset_index(drop=True)
    if len(df) < 3:
        raise ValueError("Need at least 3 tracks to draw a map.")

    t0 = time.monotonic()
    first_umap = not _umap_ready[0]
    step("Comparing songs")
    p = _prepare(df, opts)
    x = p.features
    n = len(df)

    step("Placing songs in 3D")
    emb, method = _embed_3d(x)
    step("Finding clusters")
    labels = _cluster(emb, opts.clusters)
    emb = _spread_clusters(emb, labels)

    # ---- neighbours in feature space (the "why" behind each link) -------------
    from sklearn.neighbors import NearestNeighbors

    k = max(1, min(opts.neighbors, n - 1))
    nn = NearestNeighbors(n_neighbors=k + 1).fit(x)
    dist, ind = nn.kneighbors(x)
    scale = np.median(dist[:, 1:]) or 1.0

    edges: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for i in range(n):
        for d, j in zip(dist[i, 1:], ind[i, 1:]):
            a, b = (i, int(j)) if i < j else (int(j), i)
            if a == b or (a, b) in edges:
                continue
            edges[(a, b)] = {
                "source": a, "target": b,
                "strength": round(float(math.exp(-d / scale)), 3),
                "bridge": bool(labels[a] != labels[b]),
            }

    # ---- clusters and their signal -------------------------------------------
    eng = p.engagement
    total_eng = float(eng.sum()) if eng is not None else 0.0
    clusters = []
    for c in sorted(set(labels.tolist())):
        idx = np.where(labels == c)[0]
        label, info = _cluster_label(p, idx)
        size_share = len(idx) / n
        entry = {"id": int(c), "label": label, "size": int(len(idx)), **info}
        if eng is not None and total_eng > 0:
            eng_share = float(eng[idx].sum()) / total_eng
            entry["listening_share"] = round(eng_share, 3)
            entry["lift"] = round(eng_share / size_share, 2)
        clusters.append(entry)

    if eng is not None and total_eng > 0:
        max_lift = max(c["lift"] for c in clusters) or 1
        for c in clusters:
            c["signal"] = round(c["lift"] / max_lift, 3)
    else:
        # Without listening data, "signal" means how tight a cluster is
        for c in clusters:
            idx = np.where(labels == c["id"])[0]
            spread = float(np.linalg.norm(emb[idx] - emb[idx].mean(axis=0), axis=1).mean()) if len(idx) > 1 else 0
            c["signal"] = spread
        spreads = [c["signal"] for c in clusters]
        lo, hi = min(spreads), max(spreads)
        for c in clusters:
            c["signal"] = round(1 - (c["signal"] - lo) / (hi - lo), 3) if hi > lo else 1.0
    clusters.sort(key=lambda c: -c["signal"])

    # ---- tracks ----------------------------------------------------------------
    title_col, artist_col, album_col = p.cols["title"], p.cols["artist"], p.cols["album"]
    tracks = []
    for i in range(n):
        row = df.iloc[i]
        t = {
            "id": i,
            "title": str(row[title_col]) if title_col and pd.notna(row[title_col]) else f"Track {i + 1}",
            "artist": p.artists[i] or None,
            "album": str(row[album_col]) if album_col and pd.notna(row[album_col]) else None,
            "genre": ", ".join(p.gname(g) for g in p.genres[i]) or None,
            "styles": [p.style_names.get(t, t) for t in p.styles[i]] or None,
            "key": p.keys[i].name if p.keys[i] else None,
            "camelot": p.keys[i].camelot if p.keys[i] else None,
            "bpm": round(float(p.bpm[i]), 1) if p.bpm is not None and np.isfinite(p.bpm[i]) else None,
            "x": round(float(emb[i, 0]), 2), "y": round(float(emb[i, 1]), 2), "z": round(float(emb[i, 2]), 2),
            "cluster": int(labels[i]),
            "engagement": round(float(eng[i]), 3) if eng is not None else None,
        }
        if p.cols["plays"]:
            v = pd.to_numeric(pd.Series([row[p.cols["plays"]]]), errors="coerce").iloc[0]
            t["plays"] = int(v) if pd.notna(v) else 0
        tracks.append(t)

    step("Finding hidden connections")
    # ---- hidden connections ------------------------------------------------------
    # Tracks in different clusters (usually different genres) that still match
    # musically: same or neighbouring key, same or half/double tempo, similar mood.
    hidden = []
    if p.musical is not None:
        m = p.musical
        km = max(1, min(25, n - 1))
        mdist, mind = NearestNeighbors(n_neighbors=km + 1).fit(m).kneighbors(m)
        mscale = np.median(mdist[:, 1:]) or 1.0
        seen = set()
        candidates = []
        for i in range(n):
            for d, j in zip(mdist[i, 1:], mind[i, 1:]):
                j = int(j)
                if labels[i] == labels[j]:
                    continue
                a, b = (i, j) if i < j else (j, i)
                if (a, b) in seen:
                    continue
                seen.add((a, b))
                candidates.append((float(d), a, b))
        candidates.sort()
        per_track: Dict[int, int] = {}
        for d, a, b in candidates:
            if per_track.get(a, 0) >= 2 or per_track.get(b, 0) >= 2:
                continue
            reasons = _pair_reasons(p, a, b)
            musical_reasons = [r for r in reasons if not r.startswith(("both ", "same artist"))]
            if len(musical_reasons) < 2:
                continue
            strength = round(float(math.exp(-d / mscale)), 3)
            hidden.append({"source": a, "target": b, "strength": strength, "reasons": reasons})
            edges[(a, b)] = {"source": a, "target": b, "strength": strength, "bridge": True,
                             "kind": "hidden", "reasons": reasons}
            per_track[a] = per_track.get(a, 0) + 1
            per_track[b] = per_track.get(b, 0) + 1
            if len(hidden) >= 15:
                break
    for e in edges.values():
        e.setdefault("kind", "similar")
        if "reasons" not in e:
            e["reasons"] = _pair_reasons(p, e["source"], e["target"])

    # ---- insights and recommendations ----------------------------------------
    insights: List[Dict[str, Any]] = []
    recommendations: List[Dict[str, Any]] = []
    if eng is not None and total_eng > 0:
        insights = _insights(p, eng)
        recommendations = _recommend(p, eng, labels, clusters)

    took = time.monotonic() - t0
    if method == "umap":
        _umap_ready[0] = True
        if n >= 200 and not first_umap:  # small maps are mostly fixed overhead; don't calibrate on them
            _build_cost[0] = 0.5 * _build_cost[0] + 0.5 * max(took - 0.5, 0.1) / n ** 1.5

    return {
        "tracks": tracks,
        "edges": list(edges.values()),
        "clusters": clusters,
        "hidden_connections": hidden,
        "insights": insights,
        "recommendations": recommendations,
        "meta": {
            "count": n,
            "method": method,
            "seconds": round(took, 1),
            "features_used": p.feature_groups,
            "has_listening_data": eng is not None,
            "columns": {k: v for k, v in p.cols.items() if v},
        },
    }


def _insights(p: _Prepared, eng: np.ndarray) -> List[Dict[str, Any]]:
    """Attributes the listener plays far more than their library share suggests."""
    found: List[Dict[str, Any]] = []

    def scan(kind: str, values: List[Any], fmt) -> None:
        lib = dict(_share(values))
        played = _share(values, eng)
        for v, s in played[:4]:
            base = lib.get(v, 0)
            if base <= 0 or s < 0.12:
                continue
            lift = s / base
            if lift >= 1.3:
                found.append({
                    "kind": kind, "value": fmt(v), "listening_share": round(s, 3),
                    "library_share": round(base, 3), "lift": round(lift, 2),
                    "text": f"{round(s * 100)}% of your listening is {fmt(v)}, "
                            f"though it's only {round(base * 100)}% of your library",
                })

    if any(p.keys):
        names = {k.camelot: k.long_name for k in p.keys if k}
        scan("key", [k.camelot if k else None for k in p.keys], lambda c: names[c])
    if p.bpm is not None:
        scan("tempo", [_bpm_bucket(b) for b in p.bpm], lambda b: b)
    if any(p.genres):
        scan("genre", [g[0] if g else None for g in p.genres], p.gname)
    found.sort(key=lambda f: -f["lift"])
    return found[:6]


def _recommend(p: _Prepared, eng: np.ndarray, labels: np.ndarray, clusters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    x = p.features
    # Your taste: the engagement-weighted centre of everything you play
    w = eng / eng.sum()
    taste = (x * w[:, None]).sum(axis=0)
    norms = np.linalg.norm(x, axis=1) * (np.linalg.norm(taste) or 1)
    sim = (x @ taste) / np.where(norms > 0, norms, 1)

    # Candidates: the least-played third of the library
    threshold = np.quantile(eng, 0.35)
    candidates = np.where(eng <= threshold)[0]
    if candidates.size == 0:
        return []

    signal = {c["id"]: c["signal"] for c in clusters}
    loved = np.argsort(-eng)[: max(3, len(eng) // 10)]
    score = sim + 0.25 * np.array([signal.get(int(labels[i]), 0) for i in range(len(eng))])

    out = []
    per_cluster: Dict[int, int] = {}
    for i in sorted(candidates, key=lambda i: -score[i]):
        c = int(labels[i])
        if per_cluster.get(c, 0) >= 4:
            continue
        per_cluster[c] = per_cluster.get(c, 0) + 1
        if len(out) >= 10:
            break
        # Explain it via the closest track you already love
        others = [j for j in loved if j != i] or [j for j in np.argsort(-eng) if j != i][:1]
        if not others:
            continue
        anchor = int(min(others, key=lambda j: np.linalg.norm(x[i] - x[j])))
        reasons = _pair_reasons(p, int(i), anchor)
        out.append({
            "id": int(i),
            "score": round(float(score[i]), 3),
            "because_you_play": anchor,
            "reasons": reasons or ["sits in the same part of your map as your favourites"],
        })
    return out
