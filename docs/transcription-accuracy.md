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

## Run it yourself

```bash
docker compose exec backend python scripts/eval_transcription.py --limit 20 --seconds 60
```

It needs `data/raw/maestro/maestro-v3.0.0.zip` (108 GB). Results go to `data/processed/eval/`.
