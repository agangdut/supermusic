# 🖐️ Playable by two hands

Tick **Playable by two hands** under the MIDI model in the Workspace, and the transcription is rewritten so a real pianist can play it with ten fingers. The download becomes a two-track file, **Right hand** and **Left hand**, and the untouched transcription is kept alongside it as `midi_original`.

## What it does

A transcription lists every pitch the model heard. For a band mix that can mean 10+ notes at once across four octaves, which no one can play. At every moment, the rewrite makes sure that:

- each hand holds **at most 5 notes**,
- each hand's notes fit in **one stretch**: an octave (small hands), a ninth (medium, the default) or a tenth (large),
- the **melody stays on top** in the right hand and the **bass stays at the bottom** in the left.

Notes that don't fit are moved to the other hand first, then folded up or down an octave so the harmony survives, and only dropped as a last resort. Long notes are let go early when the hand needs its fingers for what comes next; the sustain pedal is copied to both hands, so it still sounds held.

It works after any model. With **Stems** or **Auto** on a full band, every pitched track (vocals, guitar, bass, piano…) is folded into one piano part and drums are left out, so you get a piano reduction of the song.

## How playable is it? The score

Every result shows a `playability` block in its metrics:

| Field | Meaning |
|---|---|
| `playable_before_pct` | Share of moments in the raw transcription two hands could play |
| `playable_after_pct` | The same, after the rewrite |
| `notes_folded` / `notes_dropped` | Notes moved by an octave / removed |
| `notes_released_early` | Long notes shortened to free a finger |

You can also score any MIDI file: `POST /midi/playability` with `{"midi_path": "...", "hand_span": 14}`.

**Is the score fair?** MAESTRO's MIDI is exactly what concert pianists played, so it should score close to 100%. On 40 random MAESTRO performances (`scripts/eval_playability.py`):

| Hand size | Span (semitones) | Mean playable | Worst piece |
|---|---|---|---|
| Small | 12 | 99.64% | 98.3% |
| Medium | 14 | 99.91% | 98.9% |
| Large | 16 | 100.00% | 99.9% |

The rewrite kept 99.99% of their notes, so it leaves already-playable music alone. On a deliberately unplayable test (three MAESTRO pieces layered on top of each other) the score went from **33% to 99.8%**, keeping 99.7% of the notes.

## What it doesn't do yet

- **Speed.** It checks what the hands hold, not how fast they move. A dense band arrangement can still ask a hand to leap across the keyboard faster than anyone can. MAESTRO pianists top out around 17 chords a second per hand.
- **Arranging taste.** It keeps what fits, not what a human arranger would choose: no idiomatic left-hand patterns, no simplified rhythms.

## Would training a model help?

- **Training on MAESTRO: no.** MAESTRO is already two-hand playable, and the Piano model already gets 97% of its notes right ([accuracy](transcription-accuracy.md)). Training on it teaches transcription, not arranging.
- **A piano-cover model: probably yes, for full songs.** The two gaps above are what a model that learned from human piano covers would fix. One already exists: **Pop2Piano** (Choi & Lee, 2023), trained on about 300 hours of pop songs paired with YouTube piano covers and available pretrained through Hugging Face `transformers`. The sensible next step is to add it as a "Piano cover" mode and measure it with the score above before training anything of our own. Fine-tuning would need paired song audio plus human piano covers, which we don't have; [POP909](https://github.com/music-x-lab/POP909-Dataset) has 909 piano arrangements but no audio.

## Piano cover mode (Pop2Piano)

Pick **Piano cover** as the MIDI model to have the song arranged for piano by [Pop2Piano](https://huggingface.co/sweetcocoa/pop2piano), instead of transcribed note for note. The weights (about 1 GB) download on first use into `data/models/hf`. The API also takes `composer` (`composer1` to `composer21`), one of the 21 cover arrangers it learned from, each with its own style. Tick **Playable by two hands** as well to split the cover into left and right hand.

To compare it with transcribe-then-rewrite on your own songs:

```bash
docker compose exec backend python scripts/compare_piano_cover.py data/raw/songs
```

It prints how playable each method's raw output is, how busy it is, how much the rewrite had to change, and how often a hand has to leap more than an octave in under 0.15 s.

**Results on 12 songs** (7 from a Spotify likes playlist, mostly hip-hop and R&B, plus the 5 samples; October 2026, `--rules-model basic`):

| | Pop2Piano | General + rewrite |
|---|---|---|
| Raw playable (median) | 98.7% | 97.6% |
| Notes per second | 4 to 8 on every song but the quiet Satie piece (1.9) | 1.0 to 10.6, swings with the genre |
| Fast leaps per minute | 0 on every song | up to 33 |
| Time per song (CPU) | 11 to 31 s | 8 to 20 s |

Both are mostly playable before any rewrite, but they differ in kind. On rap, General transcription hears little pitched material (1 to 3 notes a second), so there is barely a piano part. On busy mixes, it makes a hand leap more than an octave in under 0.15 s up to 33 times a minute. Pop2Piano writes a full, steady part every time and never asks for those leaps. For a pianist, **Piano cover + Playable by two hands** is the better choice for full songs. Transcription stays the better choice when you want the notes that were actually played (solo piano, a single instrument).

## Run the check yourself

```bash
curl -o data/raw/maestro/maestro-v3.0.0-midi.zip https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0-midi.zip
docker compose exec backend python scripts/eval_playability.py data/raw/maestro/maestro-v3.0.0-midi.zip --limit 40
```
