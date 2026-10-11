"""
Playable piano: turn a transcription into something two human hands can play.

A transcription is a list of every pitch the model heard, which for a band mix
or a dense recording often means 8+ notes at once spread over four octaves.
This step rewrites the MIDI so that, at every moment:

- each hand holds at most 5 notes,
- each hand's notes fit inside one stretch (a ninth by default),
- the top line (melody) stays in the right hand and the bottom line (bass) in
  the left.

Notes that don't fit are first moved to the other hand, then folded into the
hand by octaves (keeping the harmony), and only dropped as a last resort.
Held notes are released early when the hand needs its fingers back.

`playability_report` scores any MIDI file by the same rules, so the effect can
be measured: real pianists' performances from MAESTRO score close to 100%.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.core.note_cleanup import separate_notes

FINGERS = 5
DEFAULT_SPAN = 14        # semitones: a major ninth, comfortable for most adult hands
CHORD_WINDOW = 0.035     # onsets this close together count as one chord
LEGATO_GRACE = 0.05      # a key held this little past the next onset is a legato overlap, not a held note
MIN_PITCH, MAX_PITCH = 21, 108  # the 88 keys

HAND_SPANS = {"small": 12, "medium": 14, "large": 16}


@dataclass
class _Note:
    pitch: int
    start: float
    end: float
    velocity: int
    hand: str = ""


@dataclass
class _HandState:
    centre: float
    held: List[_Note] = field(default_factory=list)


# --- Loading and grouping ----------------------------------------------------

def _load_notes(pm) -> List[_Note]:
    notes = [
        _Note(n.pitch, n.start, n.end, n.velocity)
        for inst in pm.instruments
        if not inst.is_drum
        for n in inst.notes
        if n.end > n.start
    ]
    notes.sort(key=lambda n: (n.start, n.pitch))
    return notes


def _chords(notes: List[_Note], window: float = CHORD_WINDOW) -> List[List[_Note]]:
    """Group notes whose onsets fall within `window` of the chord's first onset."""
    groups: List[List[_Note]] = []
    for n in notes:
        if groups and n.start - groups[-1][0].start <= window:
            groups[-1].append(n)
        else:
            groups.append([n])
    return groups


def _fits(pitches: List[int], span: int) -> bool:
    return not pitches or (len(pitches) <= FINGERS and max(pitches) - min(pitches) <= span)


def _two_hands_can_play(pitches: List[int], span: int) -> bool:
    p = sorted(set(pitches))
    return any(_fits(p[:k], span) and _fits(p[k:], span) for k in range(len(p) + 1))


# --- Measuring ---------------------------------------------------------------

def playability_report(midi_path: str | Path, hand_span: int = DEFAULT_SPAN) -> Dict[str, float]:
    """
    Score how playable a MIDI file is by two hands.

    At every chord onset, the keys that must be down (the new notes plus notes
    still held from before) are checked: can they be split into a left and a
    right hand of at most 5 notes each, each within `hand_span` semitones?
    """
    import pretty_midi

    notes = _load_notes(pretty_midi.PrettyMIDI(str(midi_path)))
    chords = _chords(notes)
    if not chords:
        return {"playable_pct": 100.0, "moments": 0, "unplayable_moments": 0,
                "max_keys_down": 0, "widest_chord": 0, "notes": 0}

    bad = max_down = widest = 0
    active: List[_Note] = []
    for chord in chords:
        # Judge the chord at its last onset: anything let go of by then doesn't need a finger
        t = chord[-1].start
        active = [n for n in active if n.end > t + LEGATO_GRACE] + [n for n in chord if n.end > t]
        pitches = [n.pitch for n in active]
        max_down = max(max_down, len(set(pitches)))
        widest = max(widest, max(pitches) - min(pitches))
        if not _two_hands_can_play(pitches, hand_span):
            bad += 1

    return {
        "playable_pct": round(100.0 * (len(chords) - bad) / len(chords), 1),
        "moments": len(chords),
        "unplayable_moments": bad,
        "max_keys_down": max_down,
        "widest_chord": widest,
        "notes": len(notes),
    }


# --- Rewriting ---------------------------------------------------------------

def _keep(pitches: List[int], hand: str, span: int) -> Tuple[List[int], List[int]]:
    """What one hand keeps from `pitches`: anchored on the melody (right) or bass (left)."""
    if not pitches:
        return [], []
    order = sorted(pitches, reverse=(hand == "R"))  # most important first
    anchor = order[0]
    kept = [p for p in order if abs(p - anchor) <= span][:FINGERS]
    rest = [p for p in order if p not in kept]
    return kept, rest


def _fold(pitch: int, kept: List[int], hand: str, other: List[int], span: int) -> Optional[int]:
    """Move `pitch` by octaves into the hand's reach, if its pitch class isn't already there."""
    if not kept or len(kept) >= FINGERS or pitch % 12 in {p % 12 for p in kept}:
        return None
    lo, hi = max(kept) - span, min(kept) + span
    if other:  # without crossing over the other hand
        lo, hi = (max(lo, max(other) + 1), hi) if hand == "R" else (lo, min(hi, min(other) - 1))
    for cand in sorted(range(pitch % 12, 128, 12), key=lambda c: abs(c - pitch)):
        if lo <= cand <= hi and MIN_PITCH <= cand <= MAX_PITCH:
            return cand
    return None


def _split_cost(left: List[int], right: List[int], hands: Dict[str, _HandState], span: int) -> float:
    lost = len(_keep(left, "L", span)[1]) + len(_keep(right, "R", span)[1])
    drift = 0.0
    if left:
        drift += abs(sum(left) / len(left) - hands["L"].centre)
    if right:
        drift += abs(sum(right) / len(right) - hands["R"].centre)
    return lost * 100 + drift


def _assign(chord: List[_Note], hands: Dict[str, _HandState], span: int) -> Tuple[Dict[str, List[_Note]], int, int]:
    """Split one chord between the hands. Returns notes per hand, and counts of folded and dropped notes."""
    by_pitch: Dict[int, _Note] = {}
    for n in chord:  # the same key twice in one chord is one key
        if n.pitch not in by_pitch or n.velocity > by_pitch[n.pitch].velocity:
            by_pitch[n.pitch] = n
    pitches = sorted(by_pitch)

    k = min(range(len(pitches) + 1),
            key=lambda i: _split_cost(pitches[:i], pitches[i:], hands, span))
    kept = {"L": _keep(pitches[:k], "L", span), "R": _keep(pitches[k:], "R", span)}
    out = {h: [by_pitch[p] for p in kept[h][0]] for h in ("L", "R")}
    folded = dropped = 0

    for h, other in (("R", "L"), ("L", "R")):
        for p in kept[h][1]:
            note = by_pitch[p]
            other_pitches = [n.pitch for n in out[other]]
            own_pitches = [n.pitch for n in out[h]]
            if _fits(other_pitches + [p], span) and p not in other_pitches:
                out[other].append(note)
                continue
            for target, current, rest in ((h, own_pitches, other_pitches), (other, other_pitches, own_pitches)):
                q = _fold(p, current, target, rest, span)
                if q is not None:
                    out[target].append(_Note(q, note.start, note.end, note.velocity))
                    folded += 1
                    break
            else:
                dropped += 1
    for h in out:
        for n in out[h]:
            n.hand = h
    return out, folded, dropped


def make_playable(
    midi_path: str | Path,
    out_path: str | Path | None = None,
    hand_span: int = DEFAULT_SPAN,
) -> Tuple[Path, Dict[str, float]]:
    """
    Rewrite a MIDI file so two hands can play it. Writes a two-track file
    ("Right hand", "Left hand") and returns its path plus before/after scores.
    """
    import pretty_midi

    midi_path = Path(midi_path)
    out_path = Path(out_path) if out_path else midi_path.with_name(f"{midi_path.stem}_playable.mid")
    src = pretty_midi.PrettyMIDI(str(midi_path))
    notes = _load_notes(src)

    hands = {"L": _HandState(centre=48.0), "R": _HandState(centre=72.0)}
    result: List[_Note] = []
    folded = dropped = released = 0

    for chord in _chords(notes):
        t = chord[0].start
        new, f, d = _assign(chord, hands, hand_span)
        folded += f
        dropped += d
        for h, state in hands.items():
            state.held = [n for n in state.held if n.end > t + LEGATO_GRACE]
            new_pitches = {n.pitch for n in new[h]}
            # Re-striking a held key, or running out of fingers or reach: let go of the held key
            for n in list(state.held):
                if n.pitch in new_pitches:
                    n.end, released = t, released + 1
                    state.held.remove(n)
            while state.held and not _fits([n.pitch for n in state.held + new[h]], hand_span):
                centre = sum(new_pitches) / len(new_pitches) if new_pitches else state.centre
                far = max(state.held, key=lambda n: abs(n.pitch - centre))
                far.end = max(far.start + 0.01, t)
                state.held.remove(far)
                released += 1
            state.held += new[h]
            result += new[h]
            if new[h]:
                state.centre = 0.5 * state.centre + 0.5 * sum(n.pitch for n in new[h]) / len(new[h])

    out = pretty_midi.PrettyMIDI(initial_tempo=_tempo(src))
    pedal = [cc for inst in src.instruments if not inst.is_drum for cc in inst.control_changes if cc.number in (64, 66, 67)]
    for h, name in (("R", "Right hand"), ("L", "Left hand")):
        inst = pretty_midi.Instrument(program=0, name=name)
        inst.notes = [pretty_midi.Note(n.velocity, n.pitch, n.start, n.end) for n in result if n.hand == h]
        inst.notes.sort(key=lambda n: (n.start, n.pitch))
        separate_notes(inst.notes)
        # Pedal goes on both tracks: MIDI pedal only affects its own channel
        inst.control_changes = [pretty_midi.ControlChange(cc.number, cc.value, cc.time) for cc in pedal]
        out.instruments.append(inst)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.write(str(out_path))

    before = playability_report(midi_path, hand_span)
    after = playability_report(out_path, hand_span)
    stats = {
        "hand_span": hand_span,
        "playable_before_pct": before["playable_pct"],
        "playable_after_pct": after["playable_pct"],
        "notes_before": before["notes"],
        "notes_after": after["notes"],
        "notes_folded": folded,
        "notes_dropped": dropped,
        "notes_released_early": released,
    }
    return out_path, stats


def _tempo(pm) -> float:
    _, tempi = pm.get_tempo_changes()
    return float(tempi[0]) if len(tempi) else 120.0
