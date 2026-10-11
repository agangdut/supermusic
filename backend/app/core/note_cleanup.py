"""
Keep repeated key presses visible as separate notes.

When the same key is struck again while it is still sounding, every engine
(Basic Pitch, Piano, YourMT3+, Pop2Piano) ends the first note at exactly the
moment the next one starts. About half of all repeated notes come out like
that (measured on two Pop2Piano covers). Back to back, the two notes draw as
one long bar in a piano roll, and a player that handles the note-on before
the note-off at the same instant silences the second press.

A real key has to come up before it can be struck again, so this shortens a
note that runs into the next press of the same key, leaving a small gap.
"""
from __future__ import annotations

from pathlib import Path

REPEAT_GAP = 0.03     # seconds of silence before a key is pressed again
MIN_KEEP = 0.5        # never cut a note to less than this share of its length


def separate_notes(notes) -> int:
    """Shorten notes that touch or overlap the next note of the same pitch. Returns how many changed."""
    by_pitch = {}
    for n in notes:
        by_pitch.setdefault(n.pitch, []).append(n)
    changed = 0
    for same in by_pitch.values():
        same.sort(key=lambda n: n.start)
        for a, b in zip(same, same[1:]):
            if b.start - a.end >= REPEAT_GAP:
                continue
            length = b.start - a.start
            new_end = b.start - min(REPEAT_GAP, (1 - MIN_KEEP) * length)
            if new_end != a.end and new_end > a.start:
                a.end = new_end
                changed += 1
    return changed


def separate_repeats(midi_path: str | Path) -> int:
    """Apply `separate_notes` to every pitched track of a MIDI file, in place."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))
    changed = sum(separate_notes(inst.notes) for inst in pm.instruments if not inst.is_drum)
    if changed:
        pm.write(str(midi_path))
    return changed
