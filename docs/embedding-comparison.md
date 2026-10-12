# Do music models hear songs the way the Music Map does?

`scripts/compare_embeddings.py` describes each song three ways and compares them:

- **map**: the Music Map's own features from audio (key on the Camelot wheel, tempo, energy, brightness)
- **MERT** (`m-a-p/MERT-v1-95M`): a self-supervised music model, averaged over time
- **CLAP** (`laion/clap-htsat-unfused` by default): an audio-and-text model, averaged over time

Averaging over time follows *Diffusable Latents from Structure-Agnostic Distillation* (2026): one vector per song keeps what the song sounds like and drops where in the song each sound happens.

## First run (2026-10-11, RTX 2060)

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

## CLAP re-run (2026-10-12): a different checkpoint works

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
- Next step for the map: add a time-averaged CLAP vector per song as an optional "sound" feature with its own slider, for libraries that have audio, and use it for "hidden connections" and "For you" picks.
