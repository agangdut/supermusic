"""
Draw the charts used in docs/how-it-works.md and save them to docs/img/.

    python scripts/make_guide_figures.py

Needs numpy, pandas, matplotlib, librosa, scikit-learn and umap-learn.
Benchmark numbers are copied from docs/transcription-accuracy.md and
docs/playable-piano.md; the Music Map figures run the real map code on the
bundled sample library.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img"
sys.path.insert(0, str(ROOT / "backend"))

# Reference palette (light mode)
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "font.size": 11, "axes.titlesize": 13, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": False,
})


def save(fig, name: str) -> None:
    fig.savefig(OUT / name, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("wrote", OUT / name)


# ---------------------------------------------------------------------------
# 1. Sound → spectrogram → piano roll
# ---------------------------------------------------------------------------

def audio_to_notes() -> None:
    import librosa

    sr = 22050
    # (midi pitch, start s, end s): a C major arpeggio, then a C major chord
    notes = [(60, 0.0, 0.5), (64, 0.5, 1.0), (67, 1.0, 1.5), (72, 1.5, 2.0),
             (60, 2.0, 3.2), (64, 2.0, 3.2), (67, 2.0, 3.2)]
    dur = 3.4
    y = np.zeros(int(sr * dur))
    for pitch, start, end in notes:
        f0 = librosa.midi_to_hz(pitch)
        t = np.arange(int(sr * (end - start))) / sr
        tone = sum(np.sin(2 * np.pi * f0 * h * t) / h ** 1.5 for h in range(1, 7))
        tone *= np.exp(-2.2 * t) * (1 - np.exp(-t * 200))
        s = int(sr * start)
        y[s:s + len(tone)] += tone
    y /= np.abs(y).max()

    fig, axes = plt.subplots(3, 1, figsize=(9, 7.2), sharex=True, gridspec_kw={"hspace": 0.45})
    t = np.arange(len(y)) / sr
    axes[0].plot(t, y, color=BLUE, lw=0.6)
    axes[0].set_title("1. Waveform: air pressure over time (what a .wav stores)")
    axes[0].set_ylabel("amplitude")

    mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128, fmax=4000, hop_length=256)
    db = librosa.power_to_db(mel, ref=np.max)
    freqs = librosa.mel_frequencies(n_mels=128, fmax=4000)
    axes[1].pcolormesh(np.arange(db.shape[1]) * 256 / sr, freqs, db, cmap="Blues", vmin=-60, vmax=0, shading="auto")
    axes[1].set_title("2. Mel spectrogram: which frequencies are loud when (what the models read)")
    axes[1].set_ylabel("frequency (Hz)")

    for pitch, start, end in notes:
        axes[2].barh(pitch, end - start, left=start, height=0.8, color=BLUE, edgecolor=SURFACE, linewidth=2)
    axes[2].set_yticks([60, 64, 67, 72], ["C4", "E4", "G4", "C5"])
    axes[2].set_ylim(57, 75)
    axes[2].set_title("3. Piano roll: notes with pitch, start and end (what a .mid stores)")
    axes[2].set_xlabel("time (s)")
    save(fig, "audio-to-notes.png")


# ---------------------------------------------------------------------------
# 2. What precision and recall count
# ---------------------------------------------------------------------------

def precision_recall() -> None:
    ref = [(60, 0.0), (64, 0.5), (67, 1.0), (72, 1.5), (60, 2.0), (64, 2.0), (67, 2.0)]
    pred = [(60, 0.02), (64, 0.53), (67, 1.12), (72, 1.49), (60, 2.01), (67, 2.03), (55, 2.02)]
    tol = 0.05
    matched_ref, matched_pred = set(), set()
    for i, (p, s) in enumerate(pred):
        for j, (rp, rs) in enumerate(ref):
            if j not in matched_ref and p == rp and abs(s - rs) <= tol:
                matched_ref.add(j)
                matched_pred.add(i)
                break

    fig, ax = plt.subplots(figsize=(9, 3.6))
    for j, (p, s) in enumerate(ref):
        if j not in matched_ref:
            ax.barh(p, 0.4, left=s, height=0.8, facecolor="none", edgecolor=AQUA, linewidth=2, linestyle="--", zorder=3)
    for i, (p, s) in enumerate(pred):
        color = BLUE if i in matched_pred else ORANGE
        ax.barh(p, 0.4, left=s, height=0.8, color=color, edgecolor=SURFACE, linewidth=2)
    ax.set_yticks([55, 60, 64, 67, 72], ["G3", "C4", "E4", "G4", "C5"])
    ax.set_xlabel("time (s)")
    tp, fp, fn = len(matched_pred), len(pred) - len(matched_pred), len(ref) - len(matched_ref)
    prec, rec = tp / (tp + fp), tp / (tp + fn)
    f1 = 2 * prec * rec / (prec + rec)
    ax.set_title(f"Scoring a transcription: precision {prec:.2f}, recall {rec:.2f}, F1 {f1:.2f}")
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=BLUE, label=f"correct: right pitch, onset within 50 ms ({tp})"),
        plt.Rectangle((0, 0), 1, 1, color=ORANGE, label=f"wrong: not in the reference, or too late ({fp})"),
        plt.Rectangle((0, 0), 1, 1, facecolor="none", edgecolor=AQUA, linestyle="--", linewidth=2,
                      label=f"missed: in the reference, not found ({fn})"),
    ]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0, -0.22), ncol=1, frameon=False)
    save(fig, "precision-recall.png")


# ---------------------------------------------------------------------------
# 3. Benchmarks
# ---------------------------------------------------------------------------

def bar_labels(ax, bars, fmt="{:.2f}") -> None:
    for b in bars:
        ax.text(b.get_width() + 0.01, b.get_y() + b.get_height() / 2, fmt.format(b.get_width()),
                va="center", color=INK, fontsize=10)


def solo_piano_benchmark() -> None:
    rows = [  # model, note F1, avg seconds per 60 s clip
        ("Basic Pitch (defaults)", 0.703, 2.9),
        ("Basic Pitch (tuned)", 0.749, 2.7),
        ("YourMT3+ (GPU)", 0.964, 8.2),
        ("Piano model (MAESTRO CRNN)", 0.974, 27.2),
    ]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.4), gridspec_kw={"wspace": 0.15})
    names = [r[0] for r in rows]
    bars = a1.barh(names, [r[1] for r in rows], color=BLUE, height=0.6)
    bar_labels(a1, bars)
    a1.set_xlim(0, 1.12)
    a1.set_title("Note F1, solo piano (higher is better)")
    a1.invert_yaxis()
    bars = a2.barh(names, [r[2] for r in rows], color=BLUE, height=0.6)
    bar_labels(a2, bars, "{:.1f}s")
    a2.set_xlim(0, 32)
    a2.set_title("Time per 60 s clip (lower is better)")
    a2.invert_yaxis()
    a2.set_yticklabels([])
    save(fig, "benchmark-solo-piano.png")


def band_benchmark() -> None:
    methods = ["General (tuned)", "Piano / Stems", "YourMT3+"]
    data = {"Precision": [0.423, 0.836, 0.939], "Recall": [0.613, 0.904, 0.901], "Note F1": [0.465, 0.867, 0.919]}
    colors = [BLUE, ORANGE, AQUA]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    y = np.arange(len(methods))
    h = 0.26
    for k, ((label, vals), c) in enumerate(zip(data.items(), colors)):
        bars = ax.barh(y + (k - 1) * h, vals, height=h, color=c, label=label, edgecolor=SURFACE, linewidth=2)
        bar_labels(ax, bars)
    ax.set_yticks(y, methods)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.1)
    ax.set_title("Piano notes recovered under a drums + bass + guitar backing")
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.12), ncol=3, frameon=False)
    save(fig, "benchmark-piano-in-band.png")


def playability_chart() -> None:
    fig, ax = plt.subplots(figsize=(7, 2.6))
    rows = [("Raw (3 pieces layered)", 33.0), ("After the two-hand rewrite", 99.8), ("Real pianists (MAESTRO)", 99.91)]
    bars = ax.barh([r[0] for r in rows], [r[1] for r in rows], color=BLUE, height=0.55)
    for b in bars:
        ax.text(b.get_width() + 1, b.get_y() + b.get_height() / 2, f"{b.get_width():.1f}%", va="center", fontsize=10)
    ax.set_xlim(0, 115)
    ax.invert_yaxis()
    ax.set_title("Share of moments two hands can play (ninth stretch)")
    save(fig, "playability.png")


# ---------------------------------------------------------------------------
# 4. Music Map
# ---------------------------------------------------------------------------

def feature_encoding() -> None:
    from app.core.music_map import _CAMELOT_MAJOR, _CAMELOT_MINOR, _NAMES

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.8), subplot_kw={"projection": "polar"})
    for table, r, minor in ((_CAMELOT_MAJOR, 1.0, False), (_CAMELOT_MINOR, 0.7, True)):
        for pc, num in table.items():
            ang = 2 * math.pi * (num - 1) / 12
            a1.plot(ang, r, "o", color=ORANGE if minor else BLUE, markersize=9)
            a1.text(ang, r + 0.17, f"{_NAMES[pc]}{'m' if minor else ''}\n{num}{'A' if minor else 'B'}",
                    ha="center", va="center", fontsize=8)
    a1.set_ylim(0, 1.3)
    a1.set_title("Keys on the Camelot wheel\n(outer = major, inner = minor; neighbours mix well)", loc="center")

    for bpm, label in [(87, "87 BPM neo-soul\n= 174 BPM drum & bass"), (120, "120 BPM\nhouse"), (140, "140 BPM\ndubstep")]:
        ang = 2 * math.pi * (math.log2(bpm) % 1)
        a2.plot(ang, 1, "o", color=BLUE, markersize=9)
        a2.text(ang, 1.32, label, ha="center", va="center", fontsize=8)
    a2.set_ylim(0, 1.5)
    a2.set_title("Tempo folded by octaves: angle = log2(BPM) mod 1\n(87 and 174 land on the same spot)", loc="center")
    for a in (a1, a2):
        a.set_yticklabels([])
        a.set_xticklabels([])
        a.grid(color=GRID)
        a.spines["polar"].set_color(GRID)
    save(fig, "map-feature-encoding.png")


def silhouette_chart() -> None:
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    from app.core.music_map import MapOptions, _embed_3d, _prepare

    df = pd.read_csv(ROOT / "backend" / "app" / "sample_data" / "sample_library.csv")
    p = _prepare(df, MapOptions())
    emb, _ = _embed_3d(p.features)
    ks, scores = list(range(2, 11)), []
    for k in ks:
        labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(emb)
        scores.append(silhouette_score(emb, labels))
    best = ks[int(np.argmax(scores))]

    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.plot(ks, scores, color=BLUE, lw=2, marker="o", markersize=8, markeredgecolor=SURFACE, markeredgewidth=2)
    ax.annotate(f"picked k = {best}", (best, max(scores)), xytext=(10, -22), textcoords="offset points", color=INK)
    ax.set_xlabel("number of clusters k")
    ax.set_ylabel("silhouette score")
    ax.yaxis.grid(True, color=GRID)
    ax.set_title(f"Choosing k on the {len(df)}-track sample library (higher = cleaner clusters)")
    save(fig, "map-silhouette.png")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    audio_to_notes()
    precision_recall()
    solo_piano_benchmark()
    band_benchmark()
    playability_chart()
    feature_encoding()
    silhouette_chart()
