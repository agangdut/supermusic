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
