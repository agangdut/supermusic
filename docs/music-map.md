# 🌌 Music Map

The Music Map turns a spreadsheet of songs into a 3D constellation of your taste. It's built to show you patterns you wouldn't spot in a playlist: which sounds you actually gravitate to, which songs from different genres secretly belong together, and what in your library you've been overlooking.

![Music Map](img/music-map.png)

Open it at **http://localhost:3000/map**. It loads a 156-track sample library (all made-up names) so you can explore right away.

## Reading the map

| You see | It means |
|---|---|
| ⭐ A star | One track. Hover for details, click to fly to it and see what it's connected to. |
| Bigger, brighter star | You play it more |
| A coloured cloud | A **cluster**: tracks that share a sound (genre, key, tempo, mood) |
| Faint lines | Each track's closest matches |
| **Pink threads** with moving sparks | **Hidden connections**: songs from *different* clusters that still match musically |
| 🟡 Gold stars (in "For you") | **Recommendations**: tracks you rarely play that sit right next to your favourites |

Position means similarity. Two stars close together sound alike on the things you've weighted. The exact axes don't mean anything on their own.

## The three panels

**Clusters.** Every group gets a plain-language name, like *Neo-Soul · A minor · 84–95 BPM · upbeat*. The bar shows its **signal**. With listening data, the signal is how much more you play the cluster than its size would predict: a cluster that is 14% of your library but 20% of your plays has a lift of 1.43×. Without listening data, it shows how tightly the tracks hang together. Click a cluster to light it up.

**Hidden links.** These are pairs from different clusters that match on at least two musical traits:
- the **same or a neighbouring key** on the Camelot wheel (the system DJs use for harmonic mixing, so A minor sits next to E minor and D minor)
- the **same tempo or half/double time**, so 87 BPM neo-soul links to 174 BPM drum & bass
- a **similar mood** (energy, valence, danceability)

They make good transitions, mashups and playlist bridges.

**For you.** This tab appears when your CSV has listening data. SuperMusic averages your most-played tracks into a "taste centre", then finds the least-played third of your library that sits closest to it. It favours clusters with high signal and never shows more than four picks from one cluster. Each pick says which favourite it resembles and why.

The **insight cards** across the top show the strongest skews in your listening, for example *"34% of your listening is Lo-Fi, though it's only 22% of your library."*

## Shape the map

The sliders change what "similar" means, from 0× (ignore) to 2× (dominant). Click **Remap** to apply.

- **Key:** turn this up to find harmonic matches across genres
- **Tempo:** groups by BPM
- **Genre:** turn it down to let sound, not labels, decide
- **Mood:** energy, valence, danceability, acousticness…
- **Artist:** pulls an artist's tracks together

## Your own CSV

Click **Map my CSV**. Column names are matched loosely (case doesn't matter), and every column is optional, but the more you include, the better the map gets. **CSV template** downloads the sample to copy from.

| What | Column names it recognises |
|---|---|
| Name | `title`, `name`, `track`, `song` |
| Artist / album | `artist`, `artists` / `album` |
| Genre | `genre`, `genres`, `style`, `tags` (split several with `;` or `,`) |
| Key | `key` as `Am`, `C#m`, `F# minor`, `Bb`, Camelot `8A`, or Spotify's `0–11` plus a `mode` column |
| Tempo | `bpm`, `tempo` |
| Mood | `energy`, `valence`, `danceability`, `acousticness`, `instrumentalness`, `speechiness`, `liveness`, `loudness` |
| Era | `year` |
| **Listening** | `play_count`, `plays`, `listens`, `streams`, `rating`, `liked`, `loved`, `skip_count` |

Exports from Spotify tools (Exportify and similar) work as they are, because they already use `key`, `mode`, `tempo`, `energy` and `valence`.

```csv
title,artist,genre,key,bpm,energy,valence,play_count,liked
Slow Letters,June Hollis,Neo-Soul,C,90,0.54,0.62,68,0
Faded Cities,Coastline Theory,Liquid DnB,Am,173,0.83,0.52,0,0
```

Limits: at least 3 tracks and at most 5,000. Under 12 tracks, the layout uses PCA instead of UMAP.

## How it works

1. **Features.** Each track becomes a vector. Keys are placed on the Camelot wheel as an angle, tempo goes on a log scale, genres and recurring artists become tags, and mood columns are standardised. Your slider weights scale each part.
2. **Layout.** UMAP squeezes the vectors into 3D, and each cluster is then opened up a little so every star is visible.
3. **Clusters.** k-means runs on the 3D layout, and the number of clusters is picked automatically by silhouette score.
4. **Links.** Each track links to its nearest neighbours. Hidden connections use a separate "musical only" space (key, tempo folded by octave, mood) and keep only pairs from different clusters.
5. **Taste.** Plays, ratings and likes combine into one score per track, with skips counting against it. Those scores drive cluster signal, insights and picks.

The code lives in [`backend/app/core/music_map.py`](../backend/app/core/music_map.py), and the 3D view in [`frontend/components/map/Graph3D.js`](../frontend/components/map/Graph3D.js). To regenerate the sample library, run `python scripts/make_sample_library.py`.

## What's next

See the [roadmap](roadmap.md#-music-map-next-steps). The big one is recommending songs that **aren't** in your library yet.
