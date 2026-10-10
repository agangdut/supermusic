# 🎹 Transcription accuracy

How well each MIDI model does on the [MAESTRO v3](https://magenta.tensorflow.org/datasets/maestro) test set: real concert-piano recordings paired with the exact MIDI the pianist played. Measured October 2026 with `scripts/eval_transcription.py` (20 randomly chosen test pieces, first 60 seconds of each, scored with `mir_eval`).


| Model | Audio | Note F1 | Precision | Recall | Note+offset F1 | Avg time |
|---|---|---|---|---|---|---|
| basic | wav | 0.703 | 0.726 | 0.715 | 0.143 | 2.9s |
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
| general | 0.393 | 0.489 | 0.396 |
| piano | 0.836 | 0.904 | 0.867 |
| stems | 0.836 | 0.904 | 0.867 |
| auto | 0.793 | 0.844 | 0.812 |

- **General** loses most of the piano under the band. Its precision also counts the band's notes as wrong, but recall (0.49) shows it misses half the piano.
- **Stems** gives the piano track to the piano model listening to the whole mix. A first version transcribed Demucs' separated piano stem instead and scored only 0.66, because separation smears piano notes.
- **Auto** chose Stems for 9 of the 10 clips and General for the one with very quiet piano (10% of the sound). It picks **Piano** for solo piano recordings (checked on three MAESTRO pieces, which measured 98–100% piano).
- This only scores the piano. The bass, guitar and other tracks that Stems also produces have no reference to score against.

## How Auto decides

Auto separates a 30-second excerpt from the middle of the song into 6 parts and measures each part's share of the sound:

| Detected | Auto uses |
|---|---|
| Piano is 60% or more | **Piano** |
| Piano is 15% or more, or drums + vocals are 25% or more | **Stems** |
| Anything else | **General** |

## Run it yourself

```bash
docker compose exec backend python scripts/eval_transcription.py --limit 20 --seconds 60
```

For the band test, pass the backing stems to use (any WAVs, for example the Stems output of a song):

```bash
docker compose exec backend python scripts/eval_mix.py --backing drums.wav bass.wav guitar.wav --limit 10 --seconds 30
```

Both need `data/raw/maestro/maestro-v3.0.0.zip` (108 GB). Results go to `data/processed/eval/`.
