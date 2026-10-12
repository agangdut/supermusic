import pretty_midi

from app.core.note_cleanup import REPEAT_GAP, separate_notes, separate_repeats


def _notes(*spans, pitch=60):
    return [pretty_midi.Note(90, pitch, s, e) for s, e in spans]


def test_back_to_back_presses_get_a_gap():
    notes = _notes((0.0, 0.5), (0.5, 1.0), (1.0, 1.5))
    assert separate_notes(notes) == 2
    assert [round(n.end, 3) for n in notes] == [0.5 - REPEAT_GAP, 1.0 - REPEAT_GAP, 1.5]
    assert [n.start for n in notes] == [0.0, 0.5, 1.0]


def test_overlapping_press_is_cut_before_the_next():
    notes = _notes((0.0, 2.0), (1.0, 1.5))
    separate_notes(notes)
    assert notes[0].end == 1.0 - REPEAT_GAP


def test_fast_repeats_keep_most_of_their_length():
    notes = _notes((0.0, 0.04), (0.04, 0.08))
    separate_notes(notes)
    assert notes[0].end == 0.02


def test_other_pitches_and_spaced_notes_untouched():
    notes = _notes((0.0, 0.5), (0.6, 1.0)) + _notes((0.0, 1.0), pitch=64)
    assert separate_notes(notes) == 0


def test_file_round_trip_skips_drums(tmp_path):
    pm = pretty_midi.PrettyMIDI()
    piano = pretty_midi.Instrument(program=0)
    piano.notes = _notes((0.0, 0.5), (0.5, 1.0))
    drums = pretty_midi.Instrument(program=0, is_drum=True)
    drums.notes = _notes((0.0, 0.5), (0.5, 1.0), pitch=36)
    pm.instruments += [piano, drums]
    f = tmp_path / "x.mid"
    pm.write(str(f))
    assert separate_repeats(f) == 1
    out = pretty_midi.PrettyMIDI(str(f))
    assert out.instruments[0].notes[0].end < out.instruments[0].notes[1].start
    assert len(out.instruments[0].notes) == 2


def _hat_song(on_hats: bool):
    import pretty_midi

    pm = pretty_midi.PrettyMIDI()
    drums = pretty_midi.Instrument(program=0, is_drum=True)
    drums.notes = [pretty_midi.Note(90, 42, 0.18 * k, 0.18 * k + 0.05) for k in range(12)]
    bass = pretty_midi.Instrument(program=33, name="Electric bass")
    shift = 0.0 if on_hats else 0.09
    bass.notes = [pretty_midi.Note(80 + k, 33, 0.18 * k + shift, 0.18 * k + shift + 0.15) for k in range(6)]
    pm.instruments = [drums, bass]
    return pm


def test_hi_hat_echo_in_the_bass_becomes_one_held_note():
    from app.core.note_cleanup import merge_hat_echoes_pm

    pm = _hat_song(on_hats=True)
    assert merge_hat_echoes_pm(pm) == 5
    (note,) = pm.instruments[1].notes
    assert note.start == 0.0 and abs(note.end - (0.18 * 5 + 0.15)) < 1e-9 and note.velocity == 85
    assert len(pm.instruments[0].notes) == 12  # drums untouched


def test_repeats_off_the_hi_hats_are_kept():
    from app.core.note_cleanup import merge_hat_echoes_pm

    pm = _hat_song(on_hats=False)
    assert merge_hat_echoes_pm(pm) == 0
    assert len(pm.instruments[1].notes) == 6
