"""The model servers on Modal: audio goes with the request, result files come back into the local folder."""
from pathlib import Path

import pytest

from app.core import modal_engines

REMOTE_OUT = "/tmp/job-x/out"


class _Remote:
    def __init__(self, fn):
        self.remote = fn
        self.remote_gen = fn


class FakeEngine:
    """Stands in for modal.Cls.from_name(...)(): records what was sent, answers like deploy/modal_app.py."""

    def __init__(self):
        self.sent = []
        self.call = _Remote(self._call)
        self.raw = _Remote(self._raw)
        self.job = _Remote(self._job)

    def _call(self, path, payload, audio):
        self.sent.append((path, payload, audio))
        if path == "/separate":
            return {"reply": {"vocals": f"{REMOTE_OUT}/htdemucs/song/vocals.wav",
                              "no_vocals": f"{REMOTE_OUT}/htdemucs/song/no_vocals.wav"},
                    "files": {"htdemucs/song/vocals.wav": b"V", "htdemucs/song/no_vocals.wav": b"A"},
                    "out_dir": REMOTE_OUT}
        if payload.get("fail"):
            return {"error": "out of GPU memory"}
        return {"reply": {"midi_path": f"{REMOTE_OUT}/model_output/song.mid"},
                "files": {"model_output/song.mid": b"MThd"}, "out_dir": REMOTE_OUT}

    def _raw(self, path, data, content_type):
        self.sent.append((path, data, content_type))
        return {"reply": {"vector": [0.5, 0.25]}}

    def _job(self, payload, audio):
        self.sent.append(("/jobs", payload, audio))
        yield {"status": "running", "completed": 1, "total": 2}
        yield {"reply": {"status": "done", "midi_path": f"{REMOTE_OUT}/audio.mid"},
               "files": {"audio.mid": b"MThd"}, "out_dir": REMOTE_OUT}


@pytest.fixture
def engine(monkeypatch):
    fake = FakeEngine()
    monkeypatch.setenv("SM_MODAL_ENGINES", "yourmt3,muscriptor,game,clap")
    monkeypatch.setattr(modal_engines, "_engine", lambda name: fake)
    return fake


@pytest.fixture
def song(tmp_path):
    p = tmp_path / "song.mp3"
    p.write_bytes(b"ID3 audio")
    return p


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("SM_MODAL_ENGINES", raising=False)
    assert not modal_engines.enabled("yourmt3")


def test_yourmt3_sends_the_audio_and_keeps_the_midi(engine, song, tmp_path):
    from app.core import yourmt3_client

    midi = yourmt3_client.transcribe_multi(song, out_dir=tmp_path / "midi")
    path, payload, audio = engine.sent[0]
    assert path == "/transcribe" and audio == ("song.mp3", b"ID3 audio")
    assert "audio_path" not in payload and "out_dir" not in payload  # local paths mean nothing there
    assert midi.read_bytes() == b"MThd" and midi.name == "song.mid" and midi.parent.parent == tmp_path / "midi"


def test_game_separation_paths_point_at_local_files(engine, tmp_path):
    from app.core import game_client
    from app.core.config import settings

    song = settings.DATA_DIR / "tests" / "song.mp3"  # it only separates files inside data/
    song.parent.mkdir(parents=True, exist_ok=True)
    song.write_bytes(b"ID3 audio")
    vocals, rest = game_client.separate_vocals(song, tmp_path / "sep")
    assert vocals.read_bytes() == b"V" and rest.read_bytes() == b"A"
    assert str(vocals).startswith(str(tmp_path / "sep"))


def test_errors_come_back_as_runtime_errors(engine, song, tmp_path):
    with pytest.raises(RuntimeError, match="out of GPU memory"):
        modal_engines.post("yourmt3", "/transcribe", {"audio_path": str(song), "out_dir": str(tmp_path), "fail": True})


def test_muscriptor_reports_progress(engine, song, tmp_path, monkeypatch):
    from app.core import muscriptor_client, progress

    seen = []
    monkeypatch.setattr(progress, "report_detail", lambda msg, **kw: seen.append(msg))
    monkeypatch.setenv("HF_TOKEN", "x")
    assert muscriptor_client.available()
    midi = muscriptor_client.transcribe_muscriptor(song, out_dir=tmp_path, dynamics=False)
    assert midi.read_bytes() == b"MThd" and midi.name == "song.mid"
    assert any("section 1 of 2" in m for m in seen)


def test_muscriptor_needs_a_token_on_modal(engine, monkeypatch):
    from app.core import muscriptor_client

    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert not muscriptor_client.available()


def test_clap_embeds_through_modal(engine):
    from app.core import sound

    assert sound.available()
    assert list(sound.embed_audio(b"wav")) == [0.5, 0.25]
    assert engine.sent[0] == ("/embed/audio", b"wav", "application/octet-stream")
