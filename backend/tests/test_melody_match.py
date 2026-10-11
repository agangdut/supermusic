import numpy as np
import pretty_midi
import soundfile as sf

from app.core.melody_match import compare, melody_match, sung_pitch

TUNE = [(60, 0.0, 0.5), (62, 0.5, 1.0), (64, 1.0, 1.5), (67, 1.5, 2.5)]  # (pitch, start, end)


def _sing(path, tune=TUNE, sr=16000):
    """A 'voice' that hums the tune, with a pause at the end."""
    y = np.zeros(int(3.0 * sr), dtype=np.float32)
    for pitch, a, b in tune:
        t = np.arange(int((b - a) * sr)) / sr
        hz = 440 * 2 ** ((pitch - 69) / 12)
        y[int(a * sr):int(a * sr) + t.size] = 0.3 * np.sin(2 * np.pi * hz * t)
    sf.write(path, y, sr)
    return path


def _midi(path, shift=0, name="Lead vocal", extra=()):
    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(53, name=name)
    for pitch, a, b in list(TUNE) + list(extra):
        inst.notes.append(pretty_midi.Note(velocity=80, pitch=pitch + shift, start=a, end=b))
    pm.instruments.append(inst)
    pm.write(str(path))
    return path


def test_matching_midi_scores_high_and_wrong_notes_low(tmp_path):
    vocals = _sing(tmp_path / "vocals.wav")
    sung = sung_pitch(vocals)
    good = melody_match(_midi(tmp_path / "good.mid"), vocals, sung=sung)
    off = melody_match(_midi(tmp_path / "off.mid", shift=1), vocals, sung=sung)
    octave = melody_match(_midi(tmp_path / "octave.mid", shift=12), vocals, sung=sung)

    assert good["melody_match"] > 85 and good["coverage"] > 85
    assert off["melody_match"] < 15
    assert octave["melody_match"] < 15 and octave["octave_ok"] > 85


def test_stray_notes_count_as_extra(tmp_path):
    vocals = _sing(tmp_path / "vocals.wav")
    sung = sung_pitch(vocals)
    clean = melody_match(_midi(tmp_path / "a.mid"), vocals, sung=sung)
    noisy = melody_match(_midi(tmp_path / "b.mid", extra=[(70, 2.6, 3.0)]), vocals, sung=sung)
    assert noisy["extra"] > clean["extra"] + 5


def test_without_a_lead_track_the_top_note_is_the_melody(tmp_path):
    vocals = _sing(tmp_path / "vocals.wav")
    path = _midi(tmp_path / "piano.mid", name="Piano")
    pm = pretty_midi.PrettyMIDI(str(path))
    pm.instruments[0].notes += [pretty_midi.Note(velocity=60, pitch=48, start=0, end=2.5)]  # a low chord tone
    pm.write(str(path))
    assert melody_match(path, vocals)["melody_match"] > 85


def test_compare_needs_singing():
    import pytest

    with pytest.raises(ValueError):
        compare(np.full(10, np.nan), np.full(10, 60.0))
