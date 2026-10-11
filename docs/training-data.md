# Data for more accurate MIDI

Researched 2026-10-11. The question: what music with matching note data could make SuperMusic's MIDI
more accurate, especially on pop songs and piano covers?

## The short version

1. **Measure pop first.** Our benchmarks ([transcription-accuracy.md](transcription-accuracy.md)) are
   piano (MAESTRO) and classical (MusicNet). Nothing tells us how good we are on pop, which is what you
   actually feed in. **MulTTiPop** (below) is a hand-checked pop test set made for exactly this. Even the
   best published model only gets 38% of pop notes right on it, so there is a lot of room.
2. **Try newer models before training our own.** Two recent open models were trained on far more data
   than we could gather on one PC: **MuScriptor** for full-band transcription (11,000 hours of real
   recordings) and **AMT-APC** for piano covers. Swapping one in is days of work; training a comparable
   model on an RTX 2060 isn't realistic.
3. **If we fine-tune, the best-fitting data is pop-song/piano-cover pairs** (Pop2Piano's list, which
   `scripts/build_cover_dataset.py` already reads, plus AMT-APC's list) and **synthetic band audio
   rendered from MIDI** (Slakh2100 and Lakh MIDI).

A quick primer: a transcription model learns from pairs of *audio* and *the notes being played in it*.
The notes must line up with the audio to within a few hundredths of a second, so the hard part of any
dataset is how those notes were obtained: played on a MIDI piano (exact), rendered from MIDI by a
synthesizer (exact but sounds less real), or aligned by hand or by algorithm to a real recording
(real sound, some timing errors).

## Pop and full-band

| Dataset | What's in it | Size | How notes were made | Licence | Fit for us |
|---|---|---|---|---|---|
| [MulTTiPop](https://huggingface.co/papers/2607.08756) (2026) | Real pop songs, every instrument | 572 clips, 3.5 h, 374 songs | Lakh MIDI aligned to the recording, checked by people | No audio shipped: YouTube IDs + MIDI. Authors say evaluation only | **Best pop test set.** Our Docker backend can fetch the YouTube clips |
| [Slakh2100](http://www.slakh.com/) | Band songs rendered from MIDI with pro sample libraries | 2,100 songs, 145 h | Exact (synthesised) | CC BY 4.0 | Good for training; YourMT3+ already learned from it |
| [Lakh MIDI](https://colinraffel.com/projects/lmd/) | 176k MIDI files, 45k matched to real songs | Huge | Hobbyist MIDI | CC BY 4.0 | Render with many soundfonts to make more Slakh-style data (MuScriptor did this with 1.45M files) |
| [RWC Popular](https://staff.aist.go.jp/m.goto/RWC-MDB/) | 100 Japanese-style pop songs recorded for research | ~7 h | Aligned MIDI | Research use, ordered from AIST | Real pop audio with notes; slow to obtain |
| [MIR-ST500](https://github.com/york135/singing_transcription_ICASSP2021) | Pop songs, sung melody only | 500 songs | Hand-labelled vocal notes, YouTube links | Research | Could help the Lead vocal track |
| [MusicNet](https://zenodo.org/records/5120004) | Classical chamber music | 330 pieces, 34 h | Aligned scores (MusicNet-EM has better timing) | CC BY 4.0 | Already our benchmark; little pop value |
| [GuitarSet](https://guitarset.weebly.com/) | Acoustic guitar | 360 clips, 3 h | Hexaphonic pickup | CC BY 4.0 | Guitar parts in pop |

## Piano and piano covers

| Dataset | What's in it | Size | Licence | Fit for us |
|---|---|---|---|---|
| [Pop2Piano list](https://github.com/sweetcocoa/pop2piano) | YouTube pop songs paired with piano covers | 5,989 covers | YouTube content; list only | Already wired up in `scripts/build_cover_dataset.py` |
| [AMT-APC](https://github.com/310hz/AMT-APC) (2024) | Songs paired with piano covers (mostly J-pop) | 332 songs, 1,267 covers | Code MIT; `download.py` fetches from YouTube | Second source of pairs, and a ready model (see below) |
| [Etude](https://xiugapurin.github.io/Etude/) (2025) | Pop/cover pairs: J-, K-, C- and Western pop | 4,752 pairs, ~500 h | Unclear whether the list is released | Largest known cover set; worth checking the project page |
| [POP909](https://github.com/music-x-lab/POP909-Dataset) | Piano arrangements of 909 Chinese pop songs (melody / bridge / accompaniment tracks) | 909 MIDI files | MIT | No audio, but a good reference for what playable pop piano looks like |
| [MAESTRO v3](https://magenta.tensorflow.org/datasets/maestro) | Concert piano on a Disklavier | 200 h | CC BY-NC-SA 4.0 | Already used; classical only, didn't help pop |
| [Aria-MIDI](https://huggingface.co/datasets/loubb/aria-midi) (2025) | Piano MIDI transcribed from YouTube | ~1M files | Research | No audio; useful as a "what real piano playing looks like" reference, not for transcription training |

## Models trained on more data than we could collect

| Model | What it does | Trained on | Licence | Notes |
|---|---|---|---|---|
| [MuScriptor](https://github.com/muscriptor/muscriptor) (2026) | Full-band transcription, all instruments | 1.45M rendered MIDI files + 11,000 h of real recordings with aligned notes | Code MIT, weights CC BY-NC 4.0 (non-commercial) | Its synthetic-only version already matches YourMT3+; adding the real recordings raised every score by about 20 points (on its own test set, no pop-only numbers). The 307M "medium" should fit the RTX 2060; 1.4B "large" probably won't. `pip install muscriptor`, weights from Hugging Face after accepting the licence |
| [AMT-APC](https://github.com/310hz/AMT-APC) (2024) | Pop song → piano cover | The cover pairs above, starting from a transcription model | MIT, weights released | Beat Pop2Piano on the paper's cover-similarity score (0.035 vs 0.090, lower is better). Has a style knob (level 1-3) |

## Suggested order

1. Build a pop benchmark from MulTTiPop's YouTube IDs (run on the Docker backend) and score General,
   Full band and Stems on it, the same way `docs/transcription-accuracy.md` does for MusicNet.
2. Add MuScriptor (medium) as an engine next to YourMT3+ and compare on that benchmark.
3. Add AMT-APC next to Pop2Piano as a second Piano cover engine and compare with `scripts/compare_piano_cover.py`.
4. Only then consider fine-tuning, using Pop2Piano + AMT-APC cover pairs for covers, or Slakh + rendered
   Lakh MIDI for full band, and judging it on the pop benchmark.
