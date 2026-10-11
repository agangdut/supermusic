# Melody match: is the tune right?

Pop songs have no answer key, so we can't measure transcription accuracy the
way the MusicNet and MAESTRO benchmarks do. But the singer *is* an answer key
for the melody: once the voice is separated, a pitch tracker can trace which
note it's on every 20 ms. Laying the MIDI's melody over that trace says how
much of the tune the transcription got right.

| Score | Meaning |
|---|---|
| **melody match** | % of sung time where the MIDI plays the same note (within half a semitone). Higher is better. |
| octave ok | Same, but a right note in the wrong octave counts. |
| coverage | % of sung time where the MIDI plays any note. |
| extra | % of the MIDI melody where nobody is singing (stray notes). Lower is better. |

The MIDI's melody is its "Lead vocal" track, or else the highest note playing
at each moment. Code: `backend/app/core/melody_match.py`.

## Where it shows up

- **In the app:** any MIDI job that separated the voice (General with "Voice as
  its own melody", or Stems with Vocals picked) shows a melody match score
  under the player.
- **API:** `POST /midi/melody-match` with `midi_path` and either `vocals_path`
  or `audio_path` (the voice is separated first).
- **Comparing modes:** `scripts/compare_melody.py` runs several modes on your
  songs and scores each against the same vocal:

      docker compose exec backend python scripts/compare_melody.py data/raw/songs --limit 10

## Limits

It only judges the melody, not chords, bass or drums. Rap has little steady
pitch, so scores there mean less. Backing vocals and harmonies that leak into
the vocal stem can pull the traced pitch off the lead line.
