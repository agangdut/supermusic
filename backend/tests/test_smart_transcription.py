from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf

from app.core.smart_transcription import GM_KICK, GM_HAT, choose_model, drums_to_notes


def test_choose_model_piano_when_piano_dominates():
    model, why = choose_model({"piano": 0.8, "other": 0.1, "bass": 0.1})
    assert model == "piano" and "piano" in why


def test_choose_model_stems_for_busy_mix():
    model, _ = choose_model({"vocals": 0.3, "drums": 0.2, "bass": 0.2, "piano": 0.3})
    assert model == "stems"


def test_choose_model_general_otherwise():
    model, why = choose_model({"guitar": 0.7, "bass": 0.2, "drums": 0.05, "vocals": 0.05})
    assert model == "basic" and "guitar" in why


def test_drums_to_notes_finds_kicks_and_hats(tmp_path):
    sr = 22050
    y = np.zeros(sr * 2, dtype=np.float32)
    t = np.arange(int(0.08 * sr)) / sr
    kick = np.sin(2 * np.pi * 55 * t) * np.exp(-t * 30)
    hat = np.random.default_rng(0).normal(size=t.size) * np.exp(-t * 80)
    hat = np.diff(np.diff(hat, prepend=0), prepend=0)  # tilt the noise towards the highs
    for start, hit in [(0.25, kick), (0.75, hat), (1.25, kick), (1.75, hat)]:
        i = int(start * sr)
        y[i:i + hit.size] += hit.astype(np.float32)
    path = tmp_path / "drums.wav"
    sf.write(path, y, sr)
    notes = drums_to_notes(path)
    pitches = [n.pitch for n in sorted(notes, key=lambda n: n.start)]
    assert pitches.count(GM_KICK) >= 2
    assert pitches.count(GM_HAT) >= 1
    assert all(isinstance(n, pretty_midi.Note) for n in notes)


def test_choose_model_stems_for_piano_in_a_band():
    model, why = choose_model({"piano": 0.3, "bass": 0.4, "guitar": 0.2, "drums": 0.1})
    assert model == "stems" and "piano" in why


def test_choose_model_prefers_yourmt3_when_running():
    assert choose_model({"guitar": 0.5, "bass": 0.3, "drums": 0.2}, multi_available=True)[0] == "multi"
    assert choose_model({"piano": 0.3, "bass": 0.7}, multi_available=True)[0] == "multi"
    # solo piano still goes to the dedicated piano model
    assert choose_model({"piano": 0.95, "other": 0.05}, multi_available=True)[0] == "piano"


def _fake_stems(tmp_path, names):
    sr = 22050
    t = np.arange(sr) / sr
    stems = {}
    for i, name in enumerate(names):
        path = tmp_path / f"{name}.wav"
        sf.write(path, (0.1 * np.sin(2 * np.pi * 220 * (i + 1) * t)).astype(np.float32), sr)
        stems[name] = str(path)
    return stems


def _fake_basic_pitch(tmp_path):
    """Stand-in for Basic Pitch: one note whose pitch says which stem it heard."""
    pitches = {"vocals": 67, "bass": 40, "guitar": 52, "other": 72}

    def run(path):
        pm = pretty_midi.PrettyMIDI()
        inst = pretty_midi.Instrument(0)
        inst.notes.append(pretty_midi.Note(velocity=80, pitch=pitches[Path(path).stem], start=0, end=0.5))
        pm.instruments.append(inst)
        out = tmp_path / f"{Path(path).stem}.mid"
        pm.write(str(out))
        return out

    return run


def test_transcribe_stems_only_the_picked_stems(tmp_path, monkeypatch):
    import app.core.smart_transcription as st

    stems = _fake_stems(tmp_path, ["vocals", "drums", "bass", "other"])
    monkeypatch.setattr(st, "transcribe_to_midi", _fake_basic_pitch(tmp_path))
    monkeypatch.setattr(st, "separate_stems", lambda *a, **k: (_ for _ in ()).throw(AssertionError("re-separated")))

    midi, info = st.transcribe_stems(tmp_path / "song.wav", out_dir=tmp_path, only=["Vocals", "bass"], stems=stems)
    assert set(info["tracks"]) == {"vocals", "bass"}
    names = {i.name for i in pretty_midi.PrettyMIDI(str(midi)).instruments}
    assert names == {"Lead vocal", "Bass"}


def test_transcribe_stems_keeps_a_quiet_stem_when_picked(tmp_path, monkeypatch):
    import app.core.smart_transcription as st

    stems = _fake_stems(tmp_path, ["vocals", "bass"])
    sf.write(stems["bass"], np.full(22050, 1e-4, dtype=np.float32), 22050)  # far below MIN_STEM_SHARE
    monkeypatch.setattr(st, "transcribe_to_midi", _fake_basic_pitch(tmp_path))

    _, everything = st.transcribe_stems(tmp_path / "song.wav", out_dir=tmp_path, stems=stems)
    _, picked = st.transcribe_stems(tmp_path / "song.wav", out_dir=tmp_path, only=["bass"], stems=stems)
    assert "bass" not in everything["tracks"]
    assert list(picked["tracks"]) == ["bass"]


def test_transcribe_stems_rejects_a_stem_that_was_not_separated(tmp_path):
    import pytest
    from app.core.smart_transcription import transcribe_stems

    with pytest.raises(ValueError, match="piano"):
        transcribe_stems(tmp_path / "song.wav", only=["piano"], stems=_fake_stems(tmp_path, ["vocals", "other"]))
