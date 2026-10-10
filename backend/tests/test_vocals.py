import pretty_midi

from app.core.vocals import MIN_NOTE, clean_melody


def note(p, s, e, v=80):
    return pretty_midi.Note(velocity=v, pitch=p, start=s, end=e)


def test_clean_melody_is_monophonic():
    notes = [note(60, 0.0, 1.0, 90), note(64, 0.2, 0.8, 50), note(67, 1.0, 2.0)]
    out = clean_melody(notes)
    for a, b in zip(out, out[1:]):
        assert a.end <= b.start + 1e-9
    assert [n.pitch for n in out] == [60, 67]  # the quieter overlapping note goes


def test_clean_melody_drops_blips_and_merges_gaps():
    notes = [note(62, 0.0, 0.5), note(62, 0.52, 1.0), note(70, 1.2, 1.2 + MIN_NOTE / 2)]
    out = clean_melody(notes)
    assert len(out) == 1 and out[0].pitch == 62 and abs(out[0].end - 1.0) < 1e-9


def test_clean_melody_drops_far_off_notes():
    notes = [note(67, i * 0.5, i * 0.5 + 0.4) for i in range(6)] + [note(38, 3.0, 3.4)]
    assert 38 not in [n.pitch for n in clean_melody(notes)]
