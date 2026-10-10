import time
from pathlib import Path

import pretty_midi
from fastapi.testclient import TestClient

import app.routes.midi as midi_routes
from app.main import app

client = TestClient(app)


def test_cover_mode_runs_pop2piano_and_can_be_made_playable(tmp_path, monkeypatch):
    calls = {}

    def fake_cover(audio_path, composer="composer1"):
        calls["composer"] = composer
        pm = pretty_midi.PrettyMIDI()
        inst = pretty_midi.Instrument(program=0)
        inst.notes = [pretty_midi.Note(80, p, 0.0, 1.0) for p in (36, 48, 60, 64, 67, 72, 76, 84)]
        pm.instruments.append(inst)
        out = tmp_path / "song_cover.mid"
        pm.write(str(out))
        return out

    monkeypatch.setattr(midi_routes, "piano_cover", fake_cover)
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"not really audio")

    job = client.post("/midi/convert", json={
        "source_path": str(audio), "model": "cover", "composer": "composer7", "playable": True,
    }).json()
    for _ in range(50):
        job = client.get(f"/midi/jobs/{job['id']}").json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.1)

    assert job["status"] == "done", job
    assert calls["composer"] == "composer7"
    assert job["result"]["metrics"]["playability"]["playable_after_pct"] == 100.0
    assert Path(job["result"]["artifacts"]["midi"]).name.endswith("_cover_playable.mid")


def test_cover_mode_rejects_unknown_composer():
    r = client.post("/midi/convert", json={"source_path": "x.wav", "model": "cover", "composer": "composer22"})
    assert r.status_code == 422
