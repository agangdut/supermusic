"""
Do MERT and CLAP hear songs the way the Music Map does?

For a set of songs with audio, this script builds three descriptions of each
song and compares them:

  map   the Music Map's audio-derived features (key on the Camelot wheel,
        tempo, energy, brightness), built with the same code the map uses
  mert  MERT-v1-95M, a self-supervised music model, averaged over time
  clap  LAION CLAP (clap-htsat-unfused), an audio-text model, averaged over time

"Averaged over time" follows the pooled-descriptor idea from
"Diffusable Latents from Structure-Agnostic Distillation" (2026): one vector
per song keeps what the song sounds like and drops where in the song it was.

It then reports, for every pair of spaces:
  * neighbour overlap@k: of each song's k nearest neighbours in space A, the
    share that are also among its k nearest in space B (chance is k/(n-1))
  * linear CKA: how alike the two spaces' overall geometry is (0..1)
and, when songs have genre labels, how often a song's neighbours share its
genre, ignoring neighbours by the same artist (so a space can't win just by
recognising a singer's voice).

Songs come from one of:
  --audio-dir DIR      every audio file under DIR (optional --labels CSV with
                       columns path,genre[,artist,title])
  --deezer             30-second previews of chart tracks from Deezer's public
                       API, labelled with the chart's genre (no key needed)

Usage (GPU strongly recommended; CPU works for a few hundred songs):

    pip install torch transformers librosa soundfile nnAudio pandas
    python scripts/compare_embeddings.py --deezer --per-genre 40
    python scripts/compare_embeddings.py --audio-dir "D:/Music" --name my_library

Output: data/processed/embeddings/<name>/ with summary.md, summary.json,
tracks.csv and the vectors (map.npy, mert.npy, mert_layers.npy, clap.npy) so
the map can reuse them later.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def _core():
    """Register app.core as a bare package so importing one module there skips the
    package __init__ (which pulls in Demucs, matplotlib and the transcription engines)."""
    import importlib
    import types

    if "app.core" not in sys.modules:
        import app

        pkg = types.ModuleType("app.core")
        pkg.__path__ = [str(ROOT / "backend" / "app" / "core")]
        sys.modules["app.core"] = pkg
        app.core = pkg
    return importlib

AUDIO_EXT = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus"}
WINDOW_S = 10.0
MAX_WINDOWS = 6

# Deezer genre ids (https://api.deezer.com/genre)
DEEZER_GENRES = {
    132: "Pop", 116: "Rap/Hip Hop", 152: "Rock", 113: "Dance", 165: "R&B",
    85: "Alternative", 106: "Electro", 129: "Jazz", 98: "Classical",
    144: "Reggae", 197: "Latin", 464: "Metal", 84: "Country", 169: "Soul & Funk",
}


# ---------------------------------------------------------------------------
# Song lists
# ---------------------------------------------------------------------------

def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "SuperMusic/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def deezer_tracks(out: Path, per_genre: int, genres: Dict[int, str]) -> pd.DataFrame:
    """Chart tracks per genre with their previews, cached under out/."""
    out.mkdir(parents=True, exist_ok=True)
    rows, seen = [], set()
    for gid, gname in genres.items():
        try:
            data = _get_json(f"https://api.deezer.com/chart/{gid}/tracks?limit={per_genre * 2}").get("data", [])
        except Exception as e:
            print(f"  {gname}: chart failed ({e})")
            continue
        kept = 0
        per_artist: Dict[str, int] = {}
        for t in data:
            if kept >= per_genre:
                break
            artist = t.get("artist", {}).get("name", "")
            # A track can chart in several genres; keep it once so its label is unambiguous
            if t["id"] in seen or not t.get("preview") or per_artist.get(artist, 0) >= 2:
                continue
            path = out / f"{t['id']}.mp3"
            if not path.exists():
                try:
                    req = urllib.request.Request(t["preview"], headers={"User-Agent": "SuperMusic/1.0"})
                    with urllib.request.urlopen(req, timeout=30) as r:
                        path.write_bytes(r.read())
                    time.sleep(0.05)
                except Exception as e:
                    print(f"  skip {artist} - {t.get('title')}: {e}")
                    continue
            seen.add(t["id"])
            per_artist[artist] = per_artist.get(artist, 0) + 1
            rows.append({"path": str(path), "artist": artist, "title": t.get("title", ""), "genre": gname})
            kept += 1
        print(f"  {gname}: {kept} tracks")
    return pd.DataFrame(rows)


def folder_tracks(audio_dir: Path, labels: Optional[Path]) -> pd.DataFrame:
    files = sorted(p for p in audio_dir.rglob("*") if p.suffix.lower() in AUDIO_EXT)
    df = pd.DataFrame({"path": [str(p) for p in files]})
    df["artist"] = ""
    df["title"] = [p.stem for p in files]
    df["genre"] = None
    if labels:
        lab = pd.read_csv(labels)
        lab["_name"] = lab["path"].map(lambda s: Path(str(s)).name.lower())
        df["_name"] = df["path"].map(lambda s: Path(s).name.lower())
        df = df.drop(columns=["artist", "title", "genre"]).merge(
            lab.drop(columns=["path"]), on="_name", how="left").drop(columns=["_name"])
        for c in ("artist", "title", "genre"):
            if c not in df:
                df[c] = None
        df["title"] = df["title"].fillna(df["path"].map(lambda s: Path(s).stem))
        df["artist"] = df["artist"].fillna("")
    return df


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

def windows(y: np.ndarray, sr: int, length_s: float = WINDOW_S, max_n: int = MAX_WINDOWS) -> List[np.ndarray]:
    """Up to max_n evenly spaced windows, skipping near-silent ones."""
    n = int(length_s * sr)
    if len(y) <= n:
        return [np.pad(y, (0, n - len(y)))]
    starts = np.linspace(0, len(y) - n, num=min(max_n, max(1, len(y) // n))).astype(int)
    wins = [y[s:s + n] for s in starts]
    loud = [w for w in wins if np.sqrt(np.mean(w ** 2)) > 1e-3]
    return loud or wins[:1]


class Mert:
    name = "m-a-p/MERT-v1-95M"
    sr = 24000

    def __init__(self, device: str):
        import torch
        from transformers import AutoModel, Wav2Vec2FeatureExtractor

        self.torch, self.device = torch, device
        self.model = AutoModel.from_pretrained(self.name, trust_remote_code=True).to(device).eval()
        self.proc = Wav2Vec2FeatureExtractor.from_pretrained(self.name, trust_remote_code=True)

    def __call__(self, wins: Sequence[np.ndarray]) -> np.ndarray:
        """(layers, dim): each layer's hidden states averaged over time and windows."""
        per_window = []
        with self.torch.no_grad():
            for w in wins:
                x = self.proc(w, sampling_rate=self.sr, return_tensors="pt").to(self.device)
                hs = self.model(**x, output_hidden_states=True).hidden_states
                per_window.append(self.torch.stack(hs).squeeze(1).mean(dim=1).float().cpu().numpy())
        return np.mean(per_window, axis=0)


def _tensor(out):
    """get_*_features returns a tensor, or an output object in newer transformers."""
    for attr in ("audio_embeds", "text_embeds", "pooler_output"):
        if hasattr(out, attr) and getattr(out, attr) is not None:
            return getattr(out, attr)
    return out


class Clap:
    sr = 48000

    def __init__(self, device: str, name: str = "laion/clap-htsat-unfused"):
        import torch
        from transformers import ClapModel, ClapProcessor

        self.torch, self.device, self.name = torch, device, name
        model, info = ClapModel.from_pretrained(name, output_loading_info=True)
        # Weights the checkpoint didn't supply start random, which quietly ruins the embeddings
        self.missing = sorted(info.get("missing_keys", []))
        if self.missing:
            print(f"  WARNING: {len(self.missing)} CLAP weights missing from {name}, e.g. {self.missing[:3]}")
        self.model = model.to(device).eval()
        self.proc = ClapProcessor.from_pretrained(name)

    def __call__(self, wins: Sequence[np.ndarray]) -> np.ndarray:
        with self.torch.no_grad():
            try:
                x = self.proc(audio=list(wins), sampling_rate=self.sr, return_tensors="pt")
            except TypeError:  # older transformers call it `audios`
                x = self.proc(audios=list(wins), sampling_rate=self.sr, return_tensors="pt")
            e = _tensor(self.model.get_audio_features(**x.to(self.device)))
            e = self.torch.nn.functional.normalize(e, dim=-1).mean(dim=0)
        return e.float().cpu().numpy()

    def text(self, queries: Sequence[str]) -> np.ndarray:
        with self.torch.no_grad():
            x = self.proc(text=list(queries), return_tensors="pt", padding=True).to(self.device)
            e = _tensor(self.model.get_text_features(**x))
            e = self.torch.nn.functional.normalize(e, dim=-1)
        return e.float().cpu().numpy()


def map_features(df: pd.DataFrame) -> np.ndarray:
    """The map's own feature vector, built by the map's code from audio-derived columns."""
    music_map = _core().import_module("app.core.music_map")
    MapOptions, _prepare = music_map.MapOptions, music_map._prepare

    cols = df[["title", "key", "bpm", "energy", "brightness"]].copy()
    return _prepare(cols, MapOptions()).features


# ---------------------------------------------------------------------------
# Comparing spaces
# ---------------------------------------------------------------------------

def _unit(x: np.ndarray) -> np.ndarray:
    x = x - x.mean(axis=0, keepdims=True)
    return x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-9)


def neighbours(x: np.ndarray, k: int, metric: str) -> np.ndarray:
    """Indices of each row's k nearest other rows."""
    if metric == "cosine":
        u = _unit(x)
        d = 1 - u @ u.T
    else:
        sq = (x ** 2).sum(axis=1)
        d = sq[:, None] + sq[None, :] - 2 * x @ x.T
    np.fill_diagonal(d, np.inf)
    return np.argsort(d, axis=1)[:, :k]


def overlap(a: np.ndarray, b: np.ndarray) -> float:
    k = a.shape[1]
    return float(np.mean([len(set(a[i]) & set(b[i])) / k for i in range(len(a))]))


def linear_cka(x: np.ndarray, y: np.ndarray) -> float:
    x = x - x.mean(axis=0)
    y = y - y.mean(axis=0)
    hsic = np.linalg.norm(y.T @ x) ** 2
    return float(hsic / (np.linalg.norm(x.T @ x) * np.linalg.norm(y.T @ y) + 1e-12))


def genre_agreement(x: np.ndarray, genres: Sequence, artists: Sequence[str], k: int, metric: str) -> float:
    """Share of each song's k nearest songs (by other artists) that share its genre."""
    nn = neighbours(x, len(x) - 1, metric)
    scores = []
    for i, row in enumerate(nn):
        if genres[i] is None:
            continue
        picked = [j for j in row if genres[j] is not None and (not artists[i] or artists[j] != artists[i])][:k]
        if picked:
            scores.append(np.mean([genres[j] == genres[i] for j in picked]))
    return float(np.mean(scores)) if scores else float("nan")


def mean_cosine(x: np.ndarray) -> float:
    """Average cosine similarity between different songs (near 1.0 means collapsed)."""
    u = x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-9)
    s = u @ u.T
    n = len(x)
    return float((s.sum() - np.trace(s)) / (n * (n - 1)))


def genre_chance(genres: Sequence) -> float:
    g = pd.Series([x for x in genres if x is not None])
    p = g.value_counts(normalize=True)
    return float((p ** 2).sum())


# ---------------------------------------------------------------------------

DEFAULT_QUERIES = [
    "sad slow piano ballad", "upbeat dance track with heavy bass", "acoustic guitar and soft singing",
    "aggressive distorted guitars", "smooth jazz with saxophone", "rap with a trap beat",
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--audio-dir", type=Path)
    src.add_argument("--deezer", action="store_true")
    ap.add_argument("--labels", type=Path, help="CSV with path,genre[,artist,title] for --audio-dir")
    ap.add_argument("--per-genre", type=int, default=40)
    ap.add_argument("--limit", type=int, default=0, help="use at most this many songs")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--name", default=None)
    ap.add_argument("--device", default=None)
    ap.add_argument("--skip", nargs="*", default=[], choices=["mert", "clap"])
    # larger_clap_music gave the same songs for every text query on 2026-10-11; see docs/embedding-comparison.md
    ap.add_argument("--clap-model", default="laion/clap-htsat-unfused",
                    help="e.g. laion/larger_clap_music, laion/larger_clap_general")
    args = ap.parse_args()

    name = args.name or ("deezer_charts" if args.deezer else args.audio_dir.name)
    out = ROOT / "data" / "processed" / "embeddings" / name
    out.mkdir(parents=True, exist_ok=True)

    print("Collecting songs ...")
    if args.deezer:
        tracks = deezer_tracks(ROOT / "data" / "raw" / "deezer_previews", args.per_genre, DEEZER_GENRES)
    else:
        tracks = folder_tracks(args.audio_dir, args.labels)
    if args.limit:
        tracks = tracks.sample(n=min(args.limit, len(tracks)), random_state=0).reset_index(drop=True)
    if len(tracks) < args.k + 2:
        sys.exit(f"Only {len(tracks)} songs found; need at least {args.k + 2}.")

    import librosa

    try:
        import torch
        device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    except ImportError:
        device = "cpu"
    print(f"{len(tracks)} songs, models on {device}")

    analyse_audio = _core().import_module("app.core.library_import").analyse_audio

    models = {}
    if "mert" not in args.skip:
        print("Loading MERT ...")
        models["mert"] = Mert(device)
    if "clap" not in args.skip:
        print("Loading CLAP ...")
        models["clap"] = Clap(device, args.clap_model)

    feats: List[dict] = []
    vecs: Dict[str, List[np.ndarray]] = {m: [] for m in models}
    keep = []
    t0 = time.time()
    for i, row in tracks.iterrows():
        try:
            y22, _ = librosa.load(row["path"], sr=22050, mono=True)
            f = analyse_audio(y22, 22050)
            if not f:
                raise ValueError("shorter than 5 s")
            out_vecs = {}
            for m, model in models.items():
                y = librosa.resample(y22, orig_sr=22050, target_sr=model.sr)
                out_vecs[m] = model(windows(y, model.sr))
        except Exception as e:
            print(f"  skip {Path(row['path']).name}: {e}")
            continue
        feats.append(f)
        for m, v in out_vecs.items():
            vecs[m].append(v)
        keep.append(i)
        if len(keep) % 25 == 0:
            print(f"  {len(keep)}/{len(tracks)}  ({time.time() - t0:.0f} s)")

    tracks = pd.concat([tracks.loc[keep].reset_index(drop=True), pd.DataFrame(feats)], axis=1)
    tracks["genre"] = tracks["genre"].where(tracks["genre"].notna(), None)
    tracks.to_csv(out / "tracks.csv", index=False)

    spaces: Dict[str, np.ndarray] = {"map": map_features(tracks)}
    metric = {"map": "euclidean"}
    np.save(out / "map.npy", spaces["map"])
    if "mert" in vecs:
        layers = np.stack(vecs["mert"])  # (n, layers, dim)
        np.save(out / "mert_layers.npy", layers)
        spaces["mert"] = layers.mean(axis=1)
        np.save(out / "mert.npy", spaces["mert"])
    if "clap" in vecs:
        spaces["clap"] = np.stack(vecs["clap"])
        np.save(out / "clap.npy", spaces["clap"])
    for s in spaces:
        metric.setdefault(s, "cosine")

    n, k = len(tracks), args.k
    nn = {s: neighbours(x, k, metric[s]) for s, x in spaces.items()}
    names = list(spaces)
    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
    result: dict = {
        "songs": n, "k": k, "device": device, "overlap_chance": k / (n - 1),
        "pairs": {f"{a}~{b}": {"overlap": overlap(nn[a], nn[b]), "cka": linear_cka(spaces[a], spaces[b])} for a, b in pairs},
    }
    genres = list(tracks["genre"])
    artists = list(tracks["artist"].fillna(""))
    labelled = sum(g is not None for g in genres)
    if labelled >= k + 2:
        result["genre"] = {
            "labelled": labelled, "chance": genre_chance(genres),
            "by_space": {s: genre_agreement(x, genres, artists, k, metric[s]) for s, x in spaces.items()},
        }
        if "mert" in vecs:
            result["genre"]["mert_by_layer"] = [
                genre_agreement(layers[:, li], genres, artists, k, "cosine") for li in range(layers.shape[1])]

    # Examples: a few songs and their 3 closest in each space
    rng = np.random.default_rng(0)
    label = lambda j: f"{tracks.at[j, 'artist']} - {tracks.at[j, 'title']}".strip(" -")
    examples = []
    for i in rng.choice(n, size=min(6, n), replace=False):
        examples.append({"song": label(i), "genre": genres[i],
                         **{s: [label(j) for j in nn[s][i][:3]] for s in names}})
    result["examples"] = examples

    # Health checks: vectors that all point the same way can't tell songs apart
    result["spread"] = {s: mean_cosine(x) for s, x in spaces.items() if s != "map"}

    if "clap" in models:
        clap = models["clap"]
        result["clap_model"] = clap.name
        result["clap_missing_weights"] = len(clap.missing)
        c = spaces["clap"] / np.linalg.norm(spaces["clap"], axis=1, keepdims=True)
        names_g = sorted({g for g in genres if g is not None})
        if len(names_g) >= 2:
            # Zero-shot: label each song with the genre whose description it sits closest to
            t = clap.text([f"This is a {g} song." for g in names_g])
            pred = [names_g[j] for j in np.argmax(c @ t.T, axis=1)]
            hits = [p == g for p, g in zip(pred, genres) if g is not None]
            result["clap_zero_shot"] = {"accuracy": float(np.mean(hits)), "chance": 1 / len(names_g)}
        q = clap.text(DEFAULT_QUERIES)
        sims = q @ c.T
        result["text_search"] = {qq: [label(j) for j in np.argsort(-sims[qi])[:5]] for qi, qq in enumerate(DEFAULT_QUERIES)}

    (out / "summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "summary.md").write_text(render(result, name), encoding="utf-8")
    print((out / "summary.md").read_text(encoding="utf-8"))
    print(f"Saved to {out}")


def render(r: dict, name: str) -> str:
    lines = [f"# Embedding comparison: {name}", "",
             f"{r['songs']} songs, k = {r['k']}. Neighbour overlap by chance would be {r['overlap_chance']:.1%}.", "",
             "| Spaces | Neighbour overlap@k | Linear CKA |", "|---|---:|---:|"]
    for p, v in r["pairs"].items():
        lines.append(f"| {p.replace('~', ' vs ')} | {v['overlap']:.1%} | {v['cka']:.2f} |")
    if "genre" in r:
        g = r["genre"]
        lines += ["", f"## Do neighbours share a genre? ({g['labelled']} labelled songs, other artists only)", "",
                  f"Chance: {g['chance']:.1%}", "", "| Space | Same-genre neighbours |", "|---|---:|"]
        for s, v in g["by_space"].items():
            lines.append(f"| {s} | {v:.1%} |")
        if "mert_by_layer" in g:
            best = int(np.nanargmax(g["mert_by_layer"]))
            lines += ["", "MERT by layer: " + ", ".join(f"{i}: {v:.0%}" for i, v in enumerate(g["mert_by_layer"]))
                      + f" (best: layer {best})"]
    lines += ["", "## Health checks", ""]
    for s, v in r.get("spread", {}).items():
        lines.append(f"- {s}: average similarity between different songs {v:.2f} (close to 1.00 means every song looks the same)")
    if "clap_model" in r:
        lines.append(f"- CLAP checkpoint: {r['clap_model']}, missing weights: {r['clap_missing_weights']}")
    if "clap_zero_shot" in r:
        z = r["clap_zero_shot"]
        lines.append(f"- CLAP zero-shot genre (\"This is a <genre> song.\"): {z['accuracy']:.1%} correct, chance {z['chance']:.1%}")
    lines += ["", "## Examples (3 closest songs in each space)", ""]
    for e in r["examples"]:
        lines.append(f"**{e['song']}**" + (f" ({e['genre']})" if e["genre"] else ""))
        for s in (k for k in e if k not in ("song", "genre")):
            lines.append(f"- {s}: " + "; ".join(e[s]))
        lines.append("")
    if "text_search" in r:
        lines += ["## CLAP text search (top 5)", ""]
        for q, hits in r["text_search"].items():
            lines.append(f"- *{q}*: " + "; ".join(hits))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
