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
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from app.core import sound as _sound

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
    # when (from streaming histories and playlist exports)
    "first_played": ("first_played",),
    "last_played": ("last_played",),
    "added": ("added_at", "date_added"),
    "playlists": ("playlists", "playlist"),
}

# Audio descriptors we use as-is when present (Spotify-style, 0..1 mostly)
AUDIO_FEATURES = (
    "energy", "danceability", "valence", "acousticness", "instrumentalness",
    "speechiness", "liveness", "loudness", "brightness",
)

# Columns that never become features (identifiers, links, our own output)
IGNORED = {"track_id", "id", "youtube_url", "url", "local_path", "path", "x", "y", "z", "isrc", "uri", "deezer_id"}


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
        "key": 1.0, "tempo": 1.0, "genre": 1.0, "mood": 1.0, "artist": 0.5, "era": 0.5, "sound": 1.0,
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


def _one_hot(values: List[List[str]], min_count: int = 1, max_vocab: Optional[int] = None) -> Tuple[np.ndarray, List[str]]:
    """Rows = tracks, columns = tags. `max_vocab` keeps only the most common tags, so a
    20,000-song library with thousands of artists doesn't become a gigabyte-sized matrix
    (rare tags barely move the layout anyway)."""
    counts: Dict[str, int] = {}
    for tags in values:
        for t in set(tags):
            counts[t] = counts.get(t, 0) + 1
    vocab = [t for t, c in counts.items() if c >= min_count]
    if max_vocab and len(vocab) > max_vocab:
        vocab = sorted(vocab, key=lambda t: (-counts[t], t))[:max_vocab]
    vocab = sorted(vocab)
    idx = {t: i for i, t in enumerate(vocab)}
    mat = np.zeros((len(values), len(vocab)), dtype=np.float32)
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
        parts.append(_liked(df, cols).astype(float))
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
    layout: np.ndarray  # what the 3D layout and links are computed from (features, compressed when large)
    feature_groups: List[str]
    mood_cols: List[str]
    mood: np.ndarray  # raw values of mood_cols (n x len(mood_cols)), NaN where missing
    mood_std: np.ndarray
    engagement: Optional[np.ndarray]
    _lib_genres: Optional[Dict[str, float]] = None  # filled in on first use by _distinctive_style
    _lib_styles: Optional[Dict[str, float]] = None
    sound: Optional[np.ndarray] = None  # CLAP vectors, centred and unit length; NaN rows = no audio
    sound_close: float = 1.0            # similarity above which two songs "sound alike"

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
        st, _ = _one_hot(styles, max_vocab=400)
        add(st, 0.6 * w["genre"], "style")

    lower = {c.lower(): c for c in df.columns}
    mood_cols = [lower[f] for f in AUDIO_FEATURES if f in lower]
    if mood_cols:
        mood = np.column_stack([_zscore(pd.to_numeric(df[c], errors="coerce").to_numpy()) for c in mood_cols])
        add(mood / math.sqrt(len(mood_cols)) * 1.6, w["mood"], "mood")

    artists = [str(v).strip() if pd.notna(v) else "" for v in df[cols["artist"]]] if cols["artist"] else [""] * len(df)
    if any(artists):
        a, vocab = _one_hot([[x.lower()] if x else [] for x in artists], min_count=2, max_vocab=1500)
        if vocab:
            add(a, 1.0 * w["artist"], "artist")

    if cols["year"]:
        yr = pd.to_numeric(df[cols["year"]], errors="coerce").to_numpy(dtype=float)
        if np.isfinite(yr).any():
            add(_zscore(yr)[:, None], 0.8 * w["era"], "era")

    # Sound: CLAP vectors describing how each song actually sounds (see app/core/sound.py)
    sound, sound_close, sb = _sound_vectors(df)
    if sb is not None:
        add(sb, 1.0 * w["sound"], "sound")

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
    if sb is not None:
        musical_blocks.append(sb)
    musical = np.hstack(musical_blocks) if len(musical_blocks) >= 2 else None

    if not blocks:
        raise ValueError(
            "Couldn't find anything to compare tracks on. Add columns such as "
            "genre, key, bpm, energy or valence."
        )

    features = np.hstack(blocks).astype(np.float32)
    raw_mood = np.column_stack([pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float) for c in mood_cols]) \
        if mood_cols else np.zeros((len(df), 0))
    with warnings.catch_warnings():  # an all-empty column has no spread; handled just below
        warnings.simplefilter("ignore", RuntimeWarning)
        mood_std = np.nanstd(raw_mood, axis=0, ddof=1) if len(df) > 1 and mood_cols else np.ones(len(mood_cols))
    mood_std = np.where(np.isfinite(mood_std) & (mood_std > 0), mood_std, 1.0)
    return _Prepared(
        df=df, cols=cols, keys=keys, bpm=bpm, genres=genres, genre_names=genre_names,
        styles=styles, style_names=style_names,
        artists=artists, musical=musical,
        features=features, layout=_compress(features), feature_groups=groups, mood_cols=mood_cols,
        mood=raw_mood, mood_std=mood_std,
        engagement=_engagement(df, cols), sound=sound, sound_close=sound_close,
    )


LAYOUT_DIMS = 48


def _compress(x: np.ndarray) -> np.ndarray:
    """Big libraries have hundreds of feature columns (one per common artist and tag).
    PCA squeezes them into LAYOUT_DIMS columns that keep almost all of the distances,
    which makes UMAP and the neighbour search many times faster."""
    n, d = x.shape
    if n < 2000 or d <= LAYOUT_DIMS * 1.5:
        return x
    from sklearn.decomposition import PCA

    return PCA(n_components=LAYOUT_DIMS, random_state=42, svd_solver="randomized").fit_transform(x).astype(np.float32)


def _has_musical(p: "_Prepared") -> np.ndarray:
    """Songs with a key, a tempo or a sound description."""
    ok = np.array([k is not None for k in p.keys], dtype=bool)
    if p.bpm is not None:
        ok |= np.isfinite(p.bpm) & (p.bpm > 0)
    if p.sound is not None:
        ok |= np.isfinite(p.sound[:, 0])
    return ok


def _sound_vectors(df: pd.DataFrame) -> Tuple[Optional[np.ndarray], float, Optional[np.ndarray]]:
    """(centred unit vectors with NaN rows, "sounds alike" threshold, feature block) from the sound column.

    Centring removes what every song shares (CLAP vectors all point roughly the same
    way), so similarity reflects how songs differ. The block is scaled to about the
    weight of the genre or mood block; songs without audio sit at the centre."""
    m = _sound.matrix(df)
    if m is None:
        return None, 1.0, None
    ok = np.isfinite(m[:, 0])
    if ok.sum() < 3:
        return None, 1.0, None
    c = m - m[ok].mean(axis=0)
    c[ok] /= np.linalg.norm(c[ok], axis=1, keepdims=True) + 1e-9
    block = np.where(ok[:, None], c, 0.0) * 1.6
    # "Sounds alike" = among the most similar 3% of pairs (sampled for big libraries)
    idx = np.where(ok)[0]
    if len(idx) > 600:
        idx = np.random.default_rng(0).choice(idx, 600, replace=False)
    sims = c[idx] @ c[idx].T
    close = float(np.quantile(sims[np.triu_indices(len(idx), 1)], 0.97)) if len(idx) > 2 else 1.0
    return c, close, block


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


BIG_MAP = 2500  # above this, clusters are drawn as dense islands with wide gaps between them


def _spread_clusters(emb: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """UMAP packs each cluster into a tight knot; open them up so every track is visible.

    Small maps open each cluster wide so every star can be clicked. Big maps keep clusters
    denser and further apart, so 20,000 stars read as separate islands rather than one fog."""
    big = len(labels) > BIG_MAP
    out = emb.copy()
    for c in set(labels.tolist()):
        idx = np.where(labels == c)[0]
        if len(idx) < 2:
            continue
        centre = emb[idx].mean(axis=0)
        offsets = emb[idx] - centre
        radius = np.linalg.norm(offsets, axis=1).mean()
        target = 6 + 1.3 * math.sqrt(len(idx)) if big else 8 + 2.4 * math.sqrt(len(idx))
        if radius > 1e-6:
            out[idx] = centre + offsets * (target / radius)
    return _separate_clusters(out, labels, gap=40.0 if big else 10.0)


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
    # clusters. Ask for roughly one cluster per ~30 tracks at least, and more
    # islands for very big libraries (about 20 for 20,000 songs).
    k_max = min(max(10, round(math.sqrt(n) / 7)), 24, max(3, n // 5))
    k_min = min(k_max, max(2, round(math.sqrt(n) / 2.5)))
    best, best_score = None, -1.0
    for k in range(k_min, k_max + 1):
        labels = KMeans(n_clusters=k, n_init=10 if n < 5000 else 4, random_state=42).fit_predict(emb)
        if k_min == k_max:
            return labels
        # Silhouette compares every pair of songs; a sample says the same for big maps
        score = silhouette_score(emb, labels, sample_size=min(n, 4000), random_state=42)
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


def _typical(idx: np.ndarray, emb: np.ndarray, eng: Optional[np.ndarray], k: int) -> List[int]:
    """The k songs that best represent a group: most played, or nearest its centre without plays."""
    if eng is not None and eng[idx].max() > 0:
        order = idx[np.argsort(-eng[idx], kind="stable")]
    else:
        order = idx[np.argsort(np.linalg.norm(emb[idx] - emb[idx].mean(axis=0), axis=1))]
    return [int(i) for i in order[:k]]


def _cluster_details(p: _Prepared, idx: np.ndarray, emb: np.ndarray, eng: Optional[np.ndarray],
                     label: str) -> Dict[str, Any]:
    """What a cluster actually contains: its artists, its most typical songs, its years, and
    for big clusters the smaller groups inside it, so a 2,000-song cluster isn't just a name."""
    out: Dict[str, Any] = {"top_tracks": _typical(idx, emb, eng, 6)}
    artists = _share([p.artists[i] or None for i in idx], eng[idx] if eng is not None and eng[idx].sum() > 0 else None)
    counts: Dict[str, int] = {}
    for i in idx:
        if p.artists[i]:
            counts[p.artists[i]] = counts.get(p.artists[i], 0) + 1
    out["top_artists"] = [{"name": a, "songs": counts.get(a, 0)} for a, _ in artists[:5]]
    if p.cols["year"]:
        yr = pd.to_numeric(p.df[p.cols["year"]].iloc[idx].astype(str).str[:4], errors="coerce").dropna()
        yr = yr[(yr > 1900) & (yr < 2100)]
        if len(yr) >= 3:
            out["years"] = [int(yr.quantile(0.1)), int(yr.quantile(0.9))]
    if len(idx) >= 250:
        from sklearn.cluster import KMeans

        k = int(min(5, max(2, round(len(idx) / 400))))
        sub = KMeans(n_clusters=k, n_init=4, random_state=42).fit_predict(emb[idx])
        parent = set(label.split(" · "))
        groups = []
        for s in range(k):
            sidx = idx[sub == s]
            if len(sidx) == 0:
                continue
            slabel, sinfo = _cluster_label(p, sidx)
            # Name it by what sets it apart from the parent ("D minor · 85–95 BPM"), not what it shares
            parts = [x for x in slabel.split(" · ") if x not in parent] or slabel.split(" · ")
            g = {"label": " · ".join(parts[:2]), "size": int(len(sidx)), "top_tracks": _typical(sidx, emb, eng, 3)}
            if eng is not None and eng[idx].sum() > 0:
                g["listening_share"] = round(float(eng[sidx].sum() / eng[idx].sum()), 3)
            groups.append(g)
        out["subgroups"] = sorted(groups, key=lambda g: -g["size"])
    return out


def _pair_reasons(p: _Prepared, i: int, j: int) -> List[str]:
    reasons: List[str] = []
    if p.sound is not None and np.isfinite(p.sound[i, 0]) and np.isfinite(p.sound[j, 0]):
        if float(p.sound[i] @ p.sound[j]) >= p.sound_close:
            reasons.append("similar sound")
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
        for m, c in enumerate(p.mood_cols):
            a, b = p.mood[i, m], p.mood[j, m]
            if np.isfinite(a) and np.isfinite(b) and abs(a - b) <= 0.25 * p.mood_std[m]:
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


def _dates(df: pd.DataFrame, col: Optional[str]) -> Optional[List[Optional[str]]]:
    if not col:
        return None
    d = pd.to_datetime(df[col], errors="coerce", utc=True)
    return [x.strftime("%Y-%m-%d") if pd.notna(x) else None for x in d]


def _track_extras(p: "_Prepared") -> Dict[str, list]:
    """Per-track values beyond the basics, only for columns the file has."""
    df, cols, out = p.df, p.cols, {}
    if cols["year"]:
        yr = pd.to_numeric(df[cols["year"]].astype(str).str[:4], errors="coerce")
        out["year"] = [int(v) if pd.notna(v) and 1900 < v < 2100 else None for v in yr]
    for m, c in enumerate(p.mood_cols):
        if c.lower() in ("energy", "valence", "danceability", "acousticness"):
            out[c.lower()] = [round(float(v), 3) if np.isfinite(v) else None for v in p.mood[:, m]]
    for name in ("first_played", "last_played", "added"):
        d = _dates(df, cols[name])
        if d is not None and any(d):
            out[name] = d
    if cols["skips"]:
        sk = pd.to_numeric(df[cols["skips"]], errors="coerce")
        out["skips"] = [int(v) if pd.notna(v) else None for v in sk]
    if cols["liked"]:
        out["liked"] = [True if v else None for v in _liked(df, cols)]
    if cols["playlists"]:
        out["playlists"] = [len([x for x in str(v).split(";") if x.strip()]) if pd.notna(v) else None
                            for v in df[cols["playlists"]]]
    return out


def _liked(df: pd.DataFrame, cols: Dict[str, Optional[str]]) -> np.ndarray:
    return df[cols["liked"]].astype(str).str.strip().str.lower().isin(
        {"1", "true", "yes", "y", "1.0", "♥", "x"}).to_numpy()


LINK_COLUMNS = {"uri", "track_uri", "spotify_uri", "spotify_url", "spotify_link", "url", "link",
                "youtube_url", "youtube_link", "youtube"}


def _links(row, cols) -> Dict[str, str]:
    """Direct Spotify/YouTube links when the CSV has them (the page falls back to a search link)."""
    out: Dict[str, str] = {}
    for c in cols:
        v = row[c]
        if not isinstance(v, str):
            continue
        v = v.strip()
        if v.startswith("spotify:track:"):
            out.setdefault("spotify_url", "https://open.spotify.com/track/" + v.split(":")[-1])
        elif v.startswith("https://open.spotify.com/"):
            out.setdefault("spotify_url", v)
        elif v.startswith(("https://www.youtube.com/", "https://youtube.com/", "https://music.youtube.com/",
                           "https://youtu.be/", "http://www.youtube.com/", "http://youtu.be/")):
            out.setdefault("youtube_url", v)
    return out


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
    x = p.layout
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

    for c in clusters:
        c.update(_cluster_details(p, np.where(labels == c["id"])[0], emb, eng, c["label"]))

    # Two clusters both called "Jazz" tell you nothing; name repeats after their main artist
    firsts: Dict[str, int] = {}
    for c in clusters:
        f = c["label"].split(" · ")[0]
        firsts[f] = firsts.get(f, 0) + 1
    for c in clusters:
        parts = c["label"].split(" · ")
        if firsts[parts[0]] > 1 and c.get("top_artists"):
            parts[0] = f"{parts[0]}: {c['top_artists'][0]['name']}"
            c["label"] = " · ".join(parts)

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
    link_cols = [c for c in df.columns if str(c).lower() in LINK_COLUMNS]
    titles = df[title_col].tolist() if title_col else [None] * n
    albums = df[album_col].tolist() if album_col else [None] * n
    links = df[link_cols].to_dict("records") if link_cols else None
    plays = pd.to_numeric(df[p.cols["plays"]], errors="coerce").to_numpy() if p.cols["plays"] else None
    extra = _track_extras(p)  # year, mood, dates... for the "colour by" lenses and the stats
    tracks = []
    for i in range(n):
        t = {
            "id": i,
            "title": str(titles[i]) if pd.notna(titles[i]) else f"Track {i + 1}",
            "artist": p.artists[i] or None,
            "album": str(albums[i]) if pd.notna(albums[i]) else None,
            "genre": ", ".join(p.gname(g) for g in p.genres[i]) or None,
            "styles": [p.style_names.get(t, t) for t in p.styles[i]] or None,
            "key": p.keys[i].name if p.keys[i] else None,
            "camelot": p.keys[i].camelot if p.keys[i] else None,
            "bpm": round(float(p.bpm[i]), 1) if p.bpm is not None and np.isfinite(p.bpm[i]) else None,
            "x": round(float(emb[i, 0]), 2), "y": round(float(emb[i, 1]), 2), "z": round(float(emb[i, 2]), 2),
            "cluster": int(labels[i]),
            "engagement": round(float(eng[i]), 3) if eng is not None else None,
        }
        if links:
            t.update(_links(links[i], link_cols))
        if plays is not None:
            t["plays"] = int(plays[i]) if np.isfinite(plays[i]) else 0
        for name, values in extra.items():
            v = values[i]
            if v is not None and not (isinstance(v, float) and not np.isfinite(v)):
                t[name] = v
        tracks.append(t)

    step("Finding hidden connections")
    # ---- hidden connections ------------------------------------------------------
    # Tracks in different clusters (usually different genres) that still match
    # musically: same or neighbouring key, same or half/double tempo, similar mood.
    hidden = []
    # Only songs with a key, a tempo or a sound description can match musically. Songs with
    # none of these all sit on the same spot in the musical space, so in a big library where
    # only a few songs were looked up online, they would crowd everyone's nearest neighbours.
    musical_ok = _has_musical(p)
    hidden_cap = int(min(60, max(15, musical_ok.sum() // 300)))  # ~15 for 4,500 songs, 60 at 18,000+
    if p.musical is not None and musical_ok.sum() >= 4:
        rows = np.where(musical_ok)[0]
        m = p.musical[rows]
        km = max(1, min(25, len(rows) - 1))
        mdist, mind = NearestNeighbors(n_neighbors=km + 1).fit(m).kneighbors(m)
        mind = rows[mind]  # back to library row numbers
        mscale = np.median(mdist[:, 1:]) or 1.0
        seen = set()
        candidates = []
        for r, i in enumerate(rows):
            i = int(i)
            for d, j in zip(mdist[r, 1:], mind[r, 1:]):
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
            if len(hidden) >= hidden_cap:
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

    step("Working out your stats")
    from app.core.map_stats import library_stats

    stats = library_stats(p, labels, clusters, tracks, dist[:, 1:])

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
        "stats": stats,
        "meta": {
            "count": n,
            "method": method,
            "seconds": round(took, 1),
            "features_used": p.feature_groups,
            "has_listening_data": eng is not None,
            "sound_tracks": int(np.isfinite(p.sound[:, 0]).sum()) if p.sound is not None else 0,
            # songs with a key, tempo or sound description: what hidden connections can use
            "musical_tracks": int(musical_ok.sum()),
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


def similar_tracks(df: pd.DataFrame, track_id: int, opts: Optional[MapOptions] = None,
                   limit: int = 8) -> Dict[str, Any]:
    """"Songs you may like" for one track, from the same library.

    When both songs have a CLAP sound description, how alike they sound counts for
    most of the score; the rest (or all of it, without sound) is closeness in the
    map's own features, so the sliders still shape the picks. At most two picks per
    artist, so one artist can't fill the list. With listening data, songs you rarely
    play get a small nudge up, since they are the ones you may be missing."""
    opts = opts or MapOptions()
    # Same rows (so the same ids) as build_map; empty columns dropped as the importer does
    df = df.dropna(how="all").reset_index(drop=True).dropna(axis=1, how="all")
    n = len(df)
    if not 0 <= track_id < n:
        raise ValueError(f"No track {track_id} in this library ({n} tracks).")
    p = _prepare(df, opts)

    d = np.linalg.norm(p.features - p.features[track_id], axis=1)
    scale = float(np.median(d[d > 0])) if (d > 0).any() else 1.0
    feat = np.exp(-d / (scale or 1.0))
    score, basis = feat, "features"
    if p.sound is not None and np.isfinite(p.sound[track_id, 0]):
        cos = p.sound @ p.sound[track_id]  # NaN for songs without a sound description
        has = np.isfinite(cos)
        score = np.where(has, 0.75 * (cos + 1) / 2 + 0.25 * feat, 0.6 * feat)
        basis = "sound"
    eng = p.engagement
    if eng is not None and eng.max() > 0:
        score = score + 0.05 * (1 - eng / eng.max())

    me = p.artists[track_id].lower()
    title_col = p.cols["title"]
    my_title = str(df.at[track_id, title_col]).strip().lower() if title_col else None
    picks: List[Dict[str, Any]] = []
    per_artist: Dict[str, int] = {}
    for j in np.argsort(-score):
        j = int(j)
        if j == track_id:
            continue
        artist = p.artists[j].lower()
        if title_col and artist == me and str(df.at[j, title_col]).strip().lower() == my_title:
            continue  # the same song listed twice
        if artist and per_artist.get(artist, 0) >= 2:
            continue
        per_artist[artist] = per_artist.get(artist, 0) + 1
        reasons = _pair_reasons(p, track_id, j)
        if artist and artist == me and not any(r.startswith("same artist") for r in reasons):
            reasons.append(f"same artist ({p.artists[j]})")
        pick = {"id": j, "score": round(float(score[j]), 3), "reasons": reasons}
        if eng is not None:
            pick["rarely_played"] = bool(eng[j] <= np.quantile(eng, 0.35))
        picks.append(pick)
        if len(picks) >= limit:
            break
    return {"id": track_id, "basis": basis, "results": picks}
