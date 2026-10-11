# 🎹 Transcription accuracy

How well each MIDI model does on the [MAESTRO v3](https://magenta.tensorflow.org/datasets/maestro) test set: real concert-piano recordings paired with the exact MIDI the pianist played. Measured October 2026 with `scripts/eval_transcription.py` (20 randomly chosen test pieces, first 60 seconds of each, scored with `mir_eval`).


| Model | Audio | Note F1 | Precision | Recall | Note+offset F1 | Avg time |
|---|---|---|---|---|---|---|
| basic (defaults) | wav | 0.703 | 0.726 | 0.715 | 0.143 | 2.9s |
| basic (tuned) | wav | 0.749 | 0.740 | 0.787 | 0.182 | 2.7s |
| multi (YourMT3+, GPU) | wav | 0.964 | 0.982 | 0.947 | 0.377 | 8.2s |
| basic | mp3 | 0.703 | 0.727 | 0.715 | 0.142 | 2.3s |
| piano | wav | 0.974 | 0.985 | 0.964 | 0.360 | 27.2s |
| piano | mp3 | 0.974 | 0.985 | 0.964 | 0.360 | 26.9s |

- **Note F1** counts a note as right when the pitch matches and it starts within 50 ms. 1.0 is perfect.
- **Note+offset F1** also requires the note to end at the right time. Both models score low here, because the sustain pedal makes "when a note ends" ambiguous.
- **MP3 costs nothing.** Re-encoding the clips to 128 kbps MP3 changed the scores by less than 0.001.

## What this means

- For **solo piano**, use **Piano** mode. It gets about 97% of notes right, compared with 70% for General. The worst piece scored 0.89 (Liszt's *Gnomenreigen*, which is very fast).
- The Piano model was itself trained on MAESTRO, so these scores match its published result (0.968) and are best-case for piano. Expect lower on home recordings, a piano in a band mix, or other instruments.
- Training our own model on MAESTRO wouldn't help here: there's almost no gap left on piano, and none from MP3.

## Piano inside a band

Most songs aren't solo piano, so a second test (`scripts/eval_mix.py`) mixes a band backing track (drums, bass and guitar at the same loudness as the piano) under 10 MAESTRO test clips. It then checks how many of the **piano** notes each mode gets back.

| Method | Precision | Recall | Note F1 |
|---|---|---|---|
| general (tuned) | 0.423 | 0.613 | 0.465 |
| piano | 0.836 | 0.904 | 0.867 |
| stems | 0.836 | 0.904 | 0.867 |
| **multi (YourMT3+)** | **0.939** | **0.901** | **0.919** |

- **YourMT3+** ("Full band" mode) is the most accurate here. It's a multi-instrument model, so it also writes the bass, guitar and drums on their own tracks. These numbers count only its piano tracks.
- **General** loses most of the piano under the band. Its precision also counts the band's notes as wrong, but recall (0.49) shows it misses half the piano.
- **Stems** gives the piano track to the piano model listening to the whole mix. A first version transcribed Demucs' separated piano stem instead and scored only 0.66, because separation smears piano notes.
- **Auto** chose Stems for 9 of the 10 clips and General for the one with very quiet piano (10% of the sound). It picks **Piano** for solo piano recordings (checked on three MAESTRO pieces, which measured 98–100% piano).
- This only scores the piano. The bass, guitar and other tracks that Stems also produces have no reference to score against.

## Real ensembles (MusicNet)

[MusicNet](https://zenodo.org/records/5120004)'s 10 held-out test recordings are real performances by string quartets, wind groups, solo violin and cello, piano, and violin with piano. Neither Basic Pitch nor YourMT3+ trained on them, so this is the fairest multi-instrument test. It scores every note, from any instrument, over the first 60 seconds (`scripts/eval_musicnet.py`).

| Mode | Precision | Recall | Note F1 | Avg time |
|---|---|---|---|---|
| General (tuned) | 0.561 | 0.502 | 0.524 | 3.0s |
| Stems | 0.475 | 0.573 | 0.506 | 34.6s |
| Full band (YourMT3+) | 0.691 | 0.682 | 0.686 | 8.4s |
| **Auto** | **0.698** | **0.695** | **0.696** | 25.7s |

- YourMT3+ beats General on 9 of the 10 recordings. The biggest gains are on solo cello (0.49 → 0.86), solo violin (0.41 → 0.71) and string quartets (0.37 → 0.65, 0.24 → 0.52). The one exception, a wind sextet, is a tie (0.59 vs 0.59).
- Auto edges out YourMT3+ because it sent the two solo piano sonatas to the Piano model.
- Stems doesn't help on classical ensembles: Demucs is trained on pop stems, so strings and winds get split badly.
- MusicNet's labels were aligned automatically and contain some timing errors, which caps every score. Compare the modes against each other, not against the MAESTRO numbers.

## Real pop songs (MulTTiPop)

The tests above are piano and classical music. [MulTTiPop](https://huggingface.co/datasets/gclef-cmu/multtipop) (CMU, 2026) is real pop: short sections (about 22 s each) of songs by 263 artists, with every instrument's notes lined up to the recording and checked by people. None of these models trained on it. Scored on the 169-clip dev set (about an hour of music, October 2026) with `scripts/eval_pop.py`. A note counts if it starts within 50 ms of a real one; for pitched notes, which instrument played it isn't checked.

| Mode | Pitched precision | Pitched recall | Pitched F1 | Drums F1 | Overall F1 | Avg time per clip |
|---|---|---|---|---|---|---|
| General (Basic Pitch) | 0.374 | 0.119 | 0.181 | 0.000 | 0.143 | 1.9s |
| Full band (YourMT3+) | 0.335 | 0.299 | 0.316 | 0.462 | 0.352 | 5.1s |
| **Full band (MuScriptor)** | **0.470** | **0.423** | **0.445** | **0.570** | **0.474** | 17.2s |

- **MuScriptor is the best model for pop.** It finds 42% of the real notes (YourMT3+ finds 30%) and more of what it writes is right (47% vs 34%). It's also better on drums. It takes about 3x longer, roughly 0.8 seconds per second of music on an RTX 2060.
- **Pop is much harder than piano.** Even the best model gets under half the notes, against 0.97 on solo piano. A full mix hides quiet parts (pads, backing vocals, doubled guitars) under louder ones.
- **General isn't meant for full mixes.** It catches 12% of the notes and writes no drums.
- Auto now uses MuScriptor for everything except solo piano. MuScriptor hasn't been tested on MAESTRO or MusicNet yet, so solo piano keeps the Piano model.

## Voices

A transcriber hears a singer as just another instrument. Two tests show where that goes wrong.

**1. Real songs: how many "instrument" notes are really the voice?** (`scripts/eval_vocal_leakage.py`, first 90 s.) Each song is transcribed twice: as is, and with the voice removed by Demucs. Instrument notes that only appear when the voice is there were caused by it. The last column counts the ones that land on the singer's own pitch.

| Song | Engine | Instrument notes/min | Caused by the voice /min | On the voice's pitch /min |
|---|---|---|---|---|
| Alessia Cara – Here (sung) | General | 523 | 331 | 195 |
| Alessia Cara – Here (sung) | Full band | 249 | 25 | 1 |
| Allan Rayman – Tennessee | General | 338 | 109 | 56 |
| Allan Rayman – Tennessee | Full band | 344 | 171 | 14 |
| Gunna – the time (melodic rap) | General | 341 | 168 | 131 |
| Gunna – the time (melodic rap) | Full band | 355 | 115 | 12 |
| Wale – Poor Decisions (rap) | General | 70 | 44 | 20 |
| Wale – Poor Decisions (rap) | Full band | 135 | 101 | 8 |

**General turns the voice into instrument notes**: up to 195 a minute land right on the singer's pitch. **Full band (YourMT3+) mostly doesn't**, because it puts the voice on its own "Singing Voice" track. Its remaining differences are mostly not on the voice's pitch; they come from Demucs changing the backing.

**2. Piano with a voice on top** (`scripts/eval_vocals.py`): 6 MAESTRO clips with a sung and a rapped vocal mixed in at equal loudness.

| Voice | Method | Piano F1 | Stray instrument notes /min |
|---|---|---|---|
| sung | Full band directly | **0.908** | 0 |
| sung | separate the voice first, then Full band | 0.855 | 11 |
| rap | Full band directly | **0.876** | 0 |
| rap | separate the voice first, then Full band | 0.826 | 6 |

Separating the voice before Full band makes things *worse*, because Demucs leaves artefacts in the backing.

**What the app does now** (the "Voice as its own melody" option, on by default):

- **General:** separates the voice with Demucs first, transcribes the backing without it, and adds the voice as a clean "Lead vocal" track. That removes the voice-caused notes in the table above, at the cost of about a minute of separation on a CPU.
- **Full band and Auto:** no separation. YourMT3+'s singing tracks are folded into one "Lead vocal".
- **Stems:** the vocal stem becomes a "Lead vocal" track.
- In every mode the Lead vocal is cleaned up: one note at a time (the strongest wins), blips under 80 ms dropped, tiny gaps merged, and notes more than 14 semitones from the melody's centre (bass bleed, octave errors) removed.

We don't have reference melodies for these songs, so the Lead vocal itself isn't scored yet. Rap has no fixed pitch, so its "melody" follows the speaking voice's rise and fall rather than a tune.

## How Auto decides

Auto separates a 30-second excerpt from the middle of the song into 6 parts and measures each part's share of the sound:

| Detected | Auto uses |
|---|---|
| Piano is 60% or more | **Piano** |
| Anything else, when the MuScriptor service is running with its Hugging Face token | **Full band** (MuScriptor) |
| Anything else, when only YourMT3+ is running (or MuScriptor fails) | **Full band (YourMT3+)** |
| Neither running: piano is 15% or more, or drums + vocals are 25% or more | **Stems** |
| Neither running: anything else | **General** |

## Run it yourself

```bash
docker compose exec backend python scripts/eval_transcription.py --limit 20 --seconds 60
```

For the band test, pass the backing stems to use (any WAVs, for example the Stems output of a song):

```bash
docker compose exec backend python scripts/eval_mix.py --backing drums.wav bass.wav guitar.wav --limit 10 --seconds 30
```

Both need `data/raw/maestro/maestro-v3.0.0.zip` (108 GB). Results go to `data/processed/eval/`.

For the pop test, first fetch the clips (needs YouTube access), then score:

```bash
docker compose exec backend python scripts/build_pop_benchmark.py --split dev
docker compose exec backend python scripts/eval_pop.py --split dev --methods general multi muscriptor
```
