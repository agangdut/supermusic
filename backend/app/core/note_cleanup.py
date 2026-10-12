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

HI_HATS = {42, 44, 46}  # General MIDI closed, pedal and open hi-hat
ECHO_RUN = 4            # this many same-pitch short notes in a row...
ECHO_NOTE = 0.25        # ...each shorter than this (seconds)...
ECHO_GAP = 0.05         # ...with at most this much silence between them...
ECHO_ON_HAT = 0.75      # ...and this share starting on a hi-hat hit is a hi-hat echo
HAT_TOLERANCE = 0.04    # seconds


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


def merge_hat_echoes_pm(pm) -> int:
    """Band models (MuScriptor especially) copy fast hi-hat rolls into pitched tracks:
    a held bass note or guitar chord comes out re-struck on every hat hit, which plays
    back as a machine-gun stutter. On Meek Mill "Free Game", 90% of the bass and 96%
    of the guitar notes in such runs sat on the model's own hi-hat hits. A run of
    short same-pitch notes that mostly lands on hi-hats becomes one held note.
    Returns how many notes were folded away."""
    import bisect

    hats = sorted(n.start for i in pm.instruments if i.is_drum for n in i.notes if n.pitch in HI_HATS)
    if len(hats) < ECHO_RUN * 2:
        return 0

    def on_hat(t: float) -> bool:
        k = bisect.bisect_left(hats, t)
        return any(0 <= j < len(hats) and abs(hats[j] - t) <= HAT_TOLERANCE for j in (k - 1, k))

    folded = 0
    for inst in pm.instruments:
        if inst.is_drum:
            continue
        by_pitch = {}
        for n in inst.notes:
            by_pitch.setdefault(n.pitch, []).append(n)
        drop = set()
        for same in by_pitch.values():
            same.sort(key=lambda n: n.start)
            runs, cur = [], [same[0]]
            for a, b in zip(same, same[1:]):
                if b.start - a.end <= ECHO_GAP and a.end - a.start < ECHO_NOTE and b.end - b.start < ECHO_NOTE:
                    cur.append(b)
                else:
                    runs.append(cur)
                    cur = [b]
            runs.append(cur)
            for run in runs:
                if len(run) < ECHO_RUN or sum(on_hat(n.start) for n in run) < ECHO_ON_HAT * len(run):
                    continue
                run[0].end = run[-1].end
                run[0].velocity = max(n.velocity for n in run)
                drop.update(id(n) for n in run[1:])
        if drop:
            inst.notes = [n for n in inst.notes if id(n) not in drop]
            folded += len(drop)
    return folded


def merge_hat_echoes(midi_path: str | Path) -> int:
    """Apply `merge_hat_echoes_pm` to a MIDI file, in place."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))
    folded = merge_hat_echoes_pm(pm)
    if folded:
        pm.write(str(midi_path))
    return folded


def separate_repeats(midi_path: str | Path) -> int:
    """Apply `separate_notes` to every pitched track of a MIDI file, in place."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))
    changed = sum(separate_notes(inst.notes) for inst in pm.instruments if not inst.is_drum)
    if changed:
        pm.write(str(midi_path))
    return changed
