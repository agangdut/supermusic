import pretty_midi

from app.core.humanize import can_render, humanize, render_audio


def _flat_part(path):
    """Like Pop2Piano: every note at velocity 77, no pedal."""
    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0)
    for bar in range(4):
        t = bar * 2.0
        for p in (40 + bar, 64, 67, 72 + bar):  # bass, two inner voices, melody
            inst.notes.append(pretty_midi.Note(77, p, t, t + 1.8))
    pm.instruments.append(inst)
    pm.write(str(path))
    return path


def test_humanize_voices_melody_over_accompaniment_and_adds_pedal(tmp_path):
    out = humanize(_flat_part(tmp_path / "flat.mid"), out_path=tmp_path / "human.mid")
    inst = pretty_midi.PrettyMIDI(str(out)).instruments[0]

    for t in (0.0, 2.0, 4.0, 6.0):
        chord = sorted((n for n in inst.notes if n.start == t), key=lambda n: n.pitch)
        bass, *inner, melody = chord
        assert melody.velocity > max(n.velocity for n in inner)
        assert bass.velocity > max(n.velocity for n in inner)
    assert len({n.velocity for n in inst.notes}) > 1

    pedal = [cc for cc in inst.control_changes if cc.number == 64]
    assert sum(cc.value > 0 for cc in pedal) == 4  # re-pedalled on each new bass note
    assert pedal[-1].value == 0                   # and lifted at the end


def test_existing_pedal_is_kept(tmp_path):
    src = _flat_part(tmp_path / "flat.mid")
    pm = pretty_midi.PrettyMIDI(str(src))
    pm.instruments[0].control_changes = [pretty_midi.ControlChange(64, 127, 0.0)]
    pm.write(str(src))
    inst = pretty_midi.PrettyMIDI(str(humanize(src))).instruments[0]
    assert [(cc.value, cc.time) for cc in inst.control_changes] == [(127, 0.0)]


def test_render_audio(tmp_path):
    mp3 = render_audio(_flat_part(tmp_path / "flat.mid"))
    if not can_render():
        assert mp3 is None
    else:
        assert mp3.exists() and mp3.stat().st_size > 10_000


def test_no_pedal_on_bass_or_guitar(tmp_path):
    src = _flat_part(tmp_path / "flat.mid")
    pm = pretty_midi.PrettyMIDI(str(src))
    pm.instruments[0].program = 33  # electric bass
    pm.write(str(src))
    inst = pretty_midi.PrettyMIDI(str(humanize(src))).instruments[0]
    assert not [cc for cc in inst.control_changes if cc.number == 64]
    assert len({n.velocity for n in inst.notes}) > 1
