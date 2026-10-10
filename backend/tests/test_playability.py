import pretty_midi
import pytest

from app.core.playability import make_playable, playability_report


def _write(path, chords, dur=0.5):
    """chords: list of pitch lists, one every `dur` seconds."""
    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0)
    for i, chord in enumerate(chords):
        for p in chord:
            inst.notes.append(pretty_midi.Note(90, p, i * dur, i * dur + dur * 0.9))
    pm.instruments.append(inst)
    pm.write(str(path))
    return path


def test_simple_piano_part_is_fully_playable(tmp_path):
    f = _write(tmp_path / "easy.mid", [[48, 52, 55, 72], [43, 50, 71], [48, 64, 67, 72]])
    assert playability_report(f)["playable_pct"] == 100.0


def test_too_many_notes_is_flagged(tmp_path):
    # 12 keys at once: more than ten fingers
    f = _write(tmp_path / "wall.mid", [list(range(48, 72, 2))])
    assert playability_report(f)["playable_pct"] == 0.0


def test_too_wide_for_one_hand_is_flagged(tmp_path):
    # three notes four octaves apart: one hand would have to cover two of them
    f = _write(tmp_path / "wide.mid", [[36, 60, 84]])
    assert playability_report(f)["playable_pct"] == 0.0


@pytest.mark.parametrize("span", [12, 14, 16])
def test_make_playable_fixes_dense_chords_and_keeps_melody_and_bass(tmp_path, span):
    chords = [list(range(36, 90, 3)), [30, 45, 52, 59, 64, 71, 76, 83, 88], [40, 41, 42, 43, 44, 45, 46, 80]]
    f = _write(tmp_path / "dense.mid", chords)
    out, stats = make_playable(f, hand_span=span)

    assert stats["playable_before_pct"] < 100
    assert stats["playable_after_pct"] == 100.0
    pm = pretty_midi.PrettyMIDI(str(out))
    assert [i.name for i in pm.instruments] == ["Right hand", "Left hand"]
    right, left = pm.instruments
    for i, chord in enumerate(chords):
        t = i * 0.5
        r = [n.pitch for n in right.notes if abs(n.start - t) < 1e-3]
        l = [n.pitch for n in left.notes if abs(n.start - t) < 1e-3]
        assert len(r) <= 5 and len(l) <= 5
        assert max(r) - min(r) <= span and max(l) - min(l) <= span
        assert max(r) == max(chord)  # melody stays on top
        assert min(l) == min(chord)  # bass stays at the bottom


def test_long_held_notes_are_released_when_fingers_are_needed(tmp_path):
    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0)
    for p in (48, 50, 52, 53, 55, 60, 62, 64, 65, 67):  # both hands hold five keys for 4 s
        inst.notes.append(pretty_midi.Note(80, p, 0.0, 4.0))
    inst.notes.append(pretty_midi.Note(80, 69, 1.0, 1.5))  # ...then an eleventh key arrives
    pm.instruments.append(inst)
    pm.write(str(tmp_path / "held.mid"))

    assert playability_report(tmp_path / "held.mid")["playable_pct"] < 100
    out, stats = make_playable(tmp_path / "held.mid")
    assert stats["playable_after_pct"] == 100.0
    assert stats["notes_after"] == 11
    assert stats["notes_released_early"] >= 1
