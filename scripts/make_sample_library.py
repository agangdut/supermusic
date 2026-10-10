"""
Generate the fictional sample library used by the Music Map demo.

    python scripts/make_sample_library.py

Writes backend/app/sample_data/sample_library.csv and a copy in
frontend/public/data/ so people can download it as a template.
All titles and artists are made up.
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
rng = random.Random(7)

ADJ = ["Midnight", "Velvet", "Paper", "Neon", "Quiet", "Golden", "Low", "Slow", "Static", "Blue", "Hollow",
       "Glass", "Warm", "Faded", "Silver", "Lucid", "Distant", "Soft", "Electric", "Wild", "Amber", "Rain"]
NOUN = ["Tapes", "Rooftops", "Signals", "Lanterns", "Tides", "Echoes", "Windows", "Satellites", "Gardens",
        "Mornings", "Lines", "Cities", "Waves", "Hearts", "Letters", "Engines", "Shadows", "Clouds", "Rivers"]

# (genre, artists, keys, bpm range, energy, valence, acousticness, danceability, how much the listener plays it)
SCENES = [
    ("Lo-Fi", ["Moss & Static", "Tape Garden", "Kumo Rooms"], ["Am", "Em", "Dm"], (78, 92), .30, .35, .65, .62, 3.0),
    ("Neo-Soul", ["Velour Avenue", "June Hollis"], ["Am", "Em", "C"], (84, 96), .45, .55, .45, .70, 2.2),
    ("Deep House", ["Harbor Unit", "Lune Collective"], ["Am", "Dm", "Gm"], (120, 124), .62, .48, .10, .82, 1.4),
    ("Liquid DnB", ["Coastline Theory"], ["Am", "Em"], (172, 176), .74, .50, .08, .58, 0.5),
    ("Jazz", ["The Albright Trio", "Nadia Ruelle"], ["Dm", "Am", "Bb", "F"], (90, 140), .35, .50, .85, .45, 0.9),
    ("Indie Rock", ["Paper Kites Club", "Northbound"], ["G", "D", "E", "A"], (115, 150), .78, .62, .20, .50, 0.6),
    ("Big Room EDM", ["Volt Kingdom", "DJ Prism"], ["F", "G", "C#"], (126, 130), .92, .60, .02, .74, 0.15),
    ("Classical", ["Orchestra Lumen", "Elise Varga"], ["D", "C", "Eb", "Bm"], (60, 110), .15, .35, .95, .20, 0.3),
]


def jitter(v: float, s: float = .08) -> float:
    return round(min(1, max(0, v + rng.gauss(0, s))), 3)


rows = []
used = set()
for genre, artists, keys, (lo, hi), en, va, ac, da, love in SCENES:
    count = {"Lo-Fi": 34, "Neo-Soul": 22, "Deep House": 24, "Liquid DnB": 12, "Jazz": 18,
             "Indie Rock": 20, "Big Room EDM": 14, "Classical": 12}[genre]
    for _ in range(count):
        while True:
            title = f"{rng.choice(ADJ)} {rng.choice(NOUN)}"
            if title not in used:
                used.add(title)
                break
        plays = int(max(0, rng.gauss(18 * love, 9 * love)))
        # A slice of every scene is still unheard, so there's something to recommend
        if rng.random() < 0.22:
            plays = 0
        rows.append({
            "title": title,
            "artist": rng.choice(artists),
            "genre": genre,
            "key": rng.choice(keys),
            "bpm": rng.randint(lo, hi),
            "energy": jitter(en),
            "valence": jitter(va),
            "acousticness": jitter(ac),
            "danceability": jitter(da),
            "year": rng.randint(2012, 2025),
            "play_count": plays,
            "liked": int(plays > 40 and rng.random() < 0.6),
        })

rng.shuffle(rows)
for out in (ROOT / "backend/app/sample_data/sample_library.csv", ROOT / "frontend/public/data/sample_library.csv"):
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} tracks to {out.relative_to(ROOT)}")
