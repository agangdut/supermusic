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

## The panels

**Clusters.** Every group gets a plain-language name, like *Neo-Soul · A minor · 84–95 BPM · upbeat*. The bar shows its **signal**. With listening data, the signal is how much more you play the cluster than its size would predict: a cluster that is 14% of your library but 20% of your plays has a lift of 1.43×. Without listening data, it shows how tightly the tracks hang together. Click a cluster to light it up.

**Hidden links.** These are pairs from different clusters that match on at least two musical traits:
- the **same or a neighbouring key** on the Camelot wheel (the system DJs use for harmonic mixing, so A minor sits next to E minor and D minor)
- the **same tempo or half/double time**, so 87 BPM neo-soul links to 174 BPM drum & bass
- a **similar mood** (energy, valence, danceability)
- a **similar sound**: the two songs are among the closest 3% of pairs by their CLAP sound description (only for songs that have one, see below)

They make good transitions, mashups and playlist bridges.

**For you.** This tab appears when your CSV has listening data. SuperMusic averages your most-played tracks into a "taste centre", then finds the least-played third of your library that sits closest to it. It favours clusters with high signal and never shows more than four picks from one cluster. Each pick says which favourite it resembles and why.

**Songs you may like.** Click any star (or any song in a list) and the side panel shows up to 8 songs from your library you may like if you like that one. When both songs have a sound description, how alike they sound counts for most of the score; otherwise it uses the map's own features, so the sliders still shape the picks. One artist can't fill the list (two songs each at most), songs you rarely play get a small nudge up, and each pick says why. Recommending songs you don't own yet needs an outside music catalogue (see [What's next](#whats-next)).

**Search.** This tab appears when songs have a sound description. Type what you want to hear, such as *sad slow piano* or *aggressive distorted guitars*, and the 20 closest-sounding songs light up on the map.

The **insight cards** across the top show the strongest skews in your listening, for example *"34% of your listening is Lo-Fi, though it's only 22% of your library."*

## Shape the map

The sliders change what "similar" means, from 0× (ignore) to 2× (dominant). Click **Remap** to apply.

- **Key:** turn this up to find harmonic matches across genres
- **Tempo:** groups by BPM
- **Genre:** turn it down to let sound, not labels, decide
- **Mood:** energy, valence, danceability, acousticness…
- **Artist:** pulls an artist's tracks together
- **Sound:** how songs actually sound (instruments, production, vocals), heard by an AI model. Only shown when songs have a sound description

## Sound descriptions (CLAP)

When you import with **Look up … online** ticked and the `clap` service is running (`docker compose up -d clap`), each song's 30-second Deezer preview also goes through [CLAP](https://huggingface.co/laion/clap-htsat-unfused), an AI model trained on audio paired with text descriptions. It turns the preview into 512 numbers that describe how the song sounds, and that description powers the **Sound** slider, "similar sound" hidden links, closer **For you** picks and **Search**. The import shows this as a "Listen to previews" step. It is the slow part of a big import, so you can skip it: untick **Listen to previews** before importing, or press **Skip** next to the step while it runs (songs heard so far keep their sound description and the map is drawn straight away). Songs already heard are cached, so later imports only listen to new ones.

- In a test on 560 songs, songs with similar CLAP descriptions shared a genre 39% of the time, against 16% for key, tempo and energy alone (see the research section below).
- Descriptions are saved in the library CSV as a `sound` column, so **Remap** and **Search** don't need to redo the work. They're also cached in `data/cache/sound_clap/`, so importing the same songs again is quick.
- A CSV with a `local_path` column pointing at audio files on the server uses those files instead of Deezer previews.
- CLAP runs on the CPU in about a second per song; `docker-compose.gpu.yml` puts it on the GPU. The model (a few hundred MB) downloads into `data/models/hf` the first time.
- Without the service, or without online lookups, the map works exactly as before.

## Import from Spotify or Apple Music

Click **Import Spotify / Apple Music** and pick one or more files. SuperMusic works out what each file is from its columns:

| Service | File | Where to get it |
|---|---|---|
| Spotify | Playlist CSV | [Exportify](https://exportify.net). Tick the audio features and artist data options for the best map |
| Spotify | `StreamingHistory_music_*.json` or `Streaming_History_Audio_*.json` | Spotify › Account › Privacy › Download your data (basic or extended history) |
| Apple Music | `Apple Music Play Activity.csv`, `… Track Play History.csv`, `Apple Music Library Tracks.json` | [privacy.apple.com](https://privacy.apple.com) › Request a copy of your data › Apple Media Services |
| Apple Music | Playlist export `.txt` | Music app › select a playlist › File › Library › Export Playlist… |

Pick a library or playlist file **and** a listening-history file together. Songs are matched by artist and title (ignoring "feat." credits), plays and skips are added up, and features come from whichever file has them. A play shorter than 30 seconds counts as a skip.

Listening histories don't include genre, tempo or key. With **Look up genre, tempo, key and energy online** ticked (the default), each song is looked up online. **Genre** comes from listener tags: Last.fm if you put a free `LASTFM_API_KEY` in `.env`, otherwise MusicBrainz (no key needed). Tags are boiled down to about 20 plain genres (Pop, Hip-Hop, R&B, Rock, Electronic, Latin, …), non-genre tags such as "seen live" are dropped, and each song keeps at most two. Deezer's album genre is only a last resort, because Deezer files whole albums under one coarse genre and calls a lot of non-rap music "Rap/Hip Hop". **Release year** comes from Deezer, but only from a search hit by the same artist, so a similarly titled song by someone else can't be used. The song's 30-second preview is then analysed on your computer for tempo, key (Krumhansl–Schmuckler), energy and brightness. Only song titles and artists leave your machine. Results are cached in `data/cache/deezer_v2` and `data/cache/genres` (one lookup per artist), so re-importing is quick. While it runs, the import panel shows each step, how many songs were found, not found or failed, and the time left, worked out from how long lookups and map drawing actually take on your computer. If the first lookups all fail because the services can't be reached, the rest are skipped and the panel says so. The first import takes about 1–2 seconds per song, plus about a second per new artist for MusicBrainz, for up to 1,500 songs, most-played first. Genres already in your file (for example Spotify's artist genres in an Exportify CSV) are always used as they are; the online lookup only fills in songs that have none.

The merged library is saved to `data/processed/library/`, and the sliders and **Remap** work on it like any other map.

## Your own CSV

Use the same **Import** button. Column names are matched loosely (case doesn't matter), and every column is optional, but the more you include, the better the map gets. **CSV template** downloads the sample to copy from.

| What | Column names it recognises |
|---|---|
| Name | `title`, `name`, `track`, `song` |
| Artist / album | `artist`, `artists` / `album` |
| Genre | `genre`, `genres`, `style`, `tags` (split several with `;` or `,`; `Hip-Hop/Rap` stays one genre) |
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

1. **Features.** Each track becomes a vector. Keys are placed on the Camelot wheel as an angle, tempo goes on a log scale, genres and recurring artists become tags (each song's detailed genre tags, such as Spotify's "toronto rap, pop rap, canadian pop", are also summed up into one or two broad genres like Hip-Hop or Pop; the broad genres carry most of the weight and name the clusters, so one tag that many artists share can't label everything. When most of your library is one genre, say Hip-Hop, clusters are named after the subgenre that sets them apart instead, such as West Coast Hip-Hop, Trap or Trap Soul, and a cluster where no genre leads is called a "Mix of …"), and mood columns are standardised. Your slider weights scale each part.
2. **Layout.** UMAP squeezes the vectors into 3D, and each cluster is then opened up a little so every star is visible.
3. **Clusters.** k-means runs on the 3D layout, and the number of clusters is picked automatically by silhouette score.
4. **Links.** Each track links to its nearest neighbours. Hidden connections use a separate "musical only" space (key, tempo folded by octave, mood, and sound when there is one) and keep only pairs from different clusters.
5. **Taste.** Plays, ratings and likes combine into one score per track, with skips counting against it. Those scores drive cluster signal, insights and picks.

The code lives in [`backend/app/core/music_map.py`](../backend/app/core/music_map.py), and the 3D view in [`frontend/components/map/Graph3D.js`](../frontend/components/map/Graph3D.js). To regenerate the sample library, run `python scripts/make_sample_library.py`.

## Research: would a music model map better?

The map's features are hand-picked (key, tempo, genre, mood). A music model can instead listen to each song and produce one vector for it. This experiment checked whether that groups songs better. The idea is explained for beginners in [How it works](how-it-works.md#could-a-learned-embedding-do-better-the-mert-and-clap-experiment).

**Short answer: yes.** Same-genre neighbours: CLAP (`laion/clap-htsat-unfused`) 38.7%, MERT layer 7 34%, the map's features 16.3%, chance 7.1%. CLAP also gives text search ("sad slow piano ballad") for free.

`scripts/compare_embeddings.py` describes each song three ways and compares them:

- **map**: the Music Map's own features from audio (key on the Camelot wheel, tempo, energy, brightness)
- **MERT** (`m-a-p/MERT-v1-95M`): a self-supervised music model, averaged over time
- **CLAP** (`laion/clap-htsat-unfused` by default): an audio-and-text model, averaged over time

Averaging over time follows *Diffusable Latents from Structure-Agnostic Distillation* (2026): one vector per song keeps what the song sounds like and drops where in the song each sound happens.

### First run (2026-10-11, RTX 2060)

560 Deezer chart previews (30 s each) from 14 genres, labelled with the chart's genre. The scores use k = 10 nearest neighbours.

| Spaces | Shared neighbours | Linear CKA |
|---|---:|---:|
| map vs MERT | 8.8% | 0.36 |
| map vs CLAP | 5.4% | 0.27 |
| MERT vs CLAP | 13.3% | 0.29 |

Two random spaces would share 1.8% of neighbours.

| Space | Neighbours sharing the song's genre (other artists only) |
|---|---:|
| map | 16.3% |
| MERT (average of all layers) | 28.9% |
| MERT layer 7 (best) | 34% |
| CLAP | 15.5% (suspect, see below) |

Random would be 7.1%.

**What it says**

- The map's neighbours mostly disagree with what MERT hears. Only about 1 in 11 of a song's closest matches is the same in both. Key, tempo, loudness and brightness alone are a thin description of a song.
- MERT groups songs by genre about twice as well as the map does, without ever being told about genres. Its middle layers (5 to 8) do best. The last layers are worse, probably because they're tuned to MERT's training task rather than to overall sound.
- These Deezer genre labels are noisy. A chart's genre is a marketing label, and many songs fit several genres. The absolute numbers are therefore low for every space. Compare them with each other, not with 100%.

### CLAP re-run (2026-10-12): a different checkpoint works

The first run used `laion/larger_clap_music`. Its text search returned the same five songs for every phrase, and its genre score (15.5%) was no better than the map's. Re-running with `laion/clap-htsat-unfused` on the same 560 songs:

| Space | Neighbours sharing the song's genre (other artists only) |
|---|---:|
| map | 16.3% |
| MERT (all layers / layer 7) | 28.9% / 34% |
| **CLAP, clap-htsat-unfused** | **38.7%** |
| CLAP, larger_clap_music (first run) | 15.5% |

Health checks for clap-htsat-unfused: no missing weights. The average similarity between different songs is 0.73, which is high but far from collapsed (1.00). Zero-shot genre ("This is a *genre* song.") is right 26.1% of the time; chance is 7.1%.

Text search now works. "aggressive distorted guitars" returns TOOL, AC/DC, Megadeth and Metallica. "smooth jazz with saxophone" returns Euge Groove and Stanley Clarke. "sad slow piano ballad" returns Yiruma, Olivia Belli and a Schubert impromptu. It still has misses: "rap with a trap beat" returns Com Truise and Europe, and "acoustic guitar and soft singing" puts TOOL first.

Map vs CLAP neighbour overlap is 6.8% (CKA 0.38), so CLAP also disagrees with the map's current notion of "similar".

**What this means**

- CLAP (clap-htsat-unfused) groups songs by genre best of the three, and it also gives text search for free. It is now the script's default.
- MERT's layer 7 comes second. Combining the two may beat either, but that hasn't been tested.
- Why larger_clap_music failed is unknown. The re-run of that checkpoint with the new health checks (`--clap-model laion/larger_clap_music --name clap_music`) would show whether weights are missing or every song collapses to the same vector. Until then, don't use it.
- Done (2026-10-12): the map now has a CLAP "sound" feature, slider and search. See [Sound descriptions](#sound-descriptions-clap).

## What's next

See the [roadmap](roadmap.md#-music-map-next-steps). The big one is recommending songs that **aren't** in your library yet.
