# Do music models hear songs the way the Music Map does?

`scripts/compare_embeddings.py` describes each song three ways and compares them:

- **map**: the Music Map's own features from audio (key on the Camelot wheel, tempo, energy, brightness)
- **MERT** (`m-a-p/MERT-v1-95M`): a self-supervised music model, averaged over time
- **CLAP** (`laion/larger_clap_music` by default): an audio-and-text model, averaged over time

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

**CLAP looked broken on this run.** Its text search returned the same five songs for every phrase, and its genre score was no better than the map's. A working CLAP should do much better on both. The script now reports health checks: missing weights in the checkpoint, how similar all the songs look to the model, and a zero-shot genre test. It also has a `--clap-model` option, so another checkpoint can be tried without recomputing MERT:

```
python scripts/compare_embeddings.py --deezer --skip mert --name clap_music
python scripts/compare_embeddings.py --deezer --skip mert --clap-model laion/clap-htsat-unfused --name clap_unfused
```
