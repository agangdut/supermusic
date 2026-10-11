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


def _band_midi(path):
    import pretty_midi

    pm = pretty_midi.PrettyMIDI()
    voice = pretty_midi.Instrument(program=52, name="voice")
    voice.notes = [pretty_midi.Note(velocity=80, pitch=60, start=0.0, end=0.5)]
    bass = pretty_midi.Instrument(program=33, name="electric_bass")
    bass.notes = [pretty_midi.Note(velocity=80, pitch=36, start=0.0, end=1.0)]
    pm.instruments = [voice, bass]
    pm.write(str(path))
    return path


def test_sung_lead_vocal_replaces_voice_with_game(tmp_path, monkeypatch):
    import pretty_midi

    from app.core import game_client, vocals

    sung = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0)
    # two repeated syllables back to back, plus a click that should be dropped
    inst.notes = [pretty_midi.Note(velocity=100, pitch=64, start=0.0, end=0.4),
                  pretty_midi.Note(velocity=100, pitch=64, start=0.4, end=0.8),
                  pretty_midi.Note(velocity=100, pitch=70, start=1.0, end=1.02)]
    sung.instruments = [inst]
    sung.write(str(tmp_path / "sung.mid"))

    monkeypatch.setattr(vocals, "split_vocals", lambda a: (tmp_path / "v.wav", tmp_path / "b.wav", 0.3))
    monkeypatch.setattr(game_client, "transcribe_singing", lambda v: tmp_path / "sung.mid")
    out, info = vocals.sung_lead_vocal(_band_midi(tmp_path / "band.mid"), tmp_path / "song.wav")

    pm = pretty_midi.PrettyMIDI(str(out))
    assert [i.name for i in pm.instruments] == ["Lead vocal", "electric_bass"]
    assert [n.pitch for n in pm.instruments[0].notes] == [64, 64]  # repeats kept apart, click gone
    assert info["vocal_engine"] == "GAME" and info["vocal_stem"].endswith("v.wav")


def test_sung_lead_vocal_falls_back_when_game_fails(tmp_path, monkeypatch):
    import pretty_midi

    from app.core import game_client, vocals

    def boom(v):
        raise RuntimeError("down")

    monkeypatch.setattr(vocals, "split_vocals", lambda a: (tmp_path / "v.wav", tmp_path / "b.wav", 0.3))
    monkeypatch.setattr(game_client, "transcribe_singing", boom)
    out, info = vocals.sung_lead_vocal(_band_midi(tmp_path / "band.mid"), tmp_path / "song.wav")
    names = [i.name for i in pretty_midi.PrettyMIDI(str(out)).instruments]
    assert "Lead vocal" in names and "voice" not in names
    assert "vocal_engine" not in info
