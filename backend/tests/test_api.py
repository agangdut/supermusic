import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.parametrize(
    "path",
    ["/midi/convert", "/stems/separate", "/csv/enrich", "/tracks/download"],
)
def test_job_routes_are_mounted_once(path):
    paths = app.openapi()["paths"]
    assert path in paths
    area = path.split("/")[1]
    assert f"/{area}{path}" not in paths


def test_unknown_job_is_404():
    assert client.get("/midi/jobs/does-not-exist").status_code == 404


def test_upload_csv_returns_server_path():
    r = client.post(
        "/upload/csv",
        files={"file": ("tracks.csv", b"title,artist\nSong,Band\n", "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["path"].endswith("tracks.csv")


def test_upload_rejects_wrong_extension():
    r = client.post(
        "/upload/audio",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400


def test_register_login_me():
    creds = {"username": "tester", "email": "t@example.com", "password": "correct-horse"}
    r = client.post("/auth/register", json=creds)
    assert r.status_code == 200, r.text
    r = client.post("/auth/login", json={"username": "tester", "password": "correct-horse"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "tester"


def test_register_password_length():
    r = client.post("/auth/register", json={"username": "long", "password": "é" * 40})
    assert r.status_code == 400, r.text
    r = client.post("/auth/register", json={"username": "good", "password": "x" * 8})
    assert r.status_code == 200, r.text
    r = client.post("/auth/register", json={"username": "good2", "password": "x" * 72})
    assert r.status_code == 200, r.text

def test_midi_convert_rejects_unknown_stem():
    r = client.post("/midi/convert", json={"source_path": "x.wav", "model": "stems", "stems": ["kazoo"]})
    assert r.status_code == 422


def test_midi_convert_from_missing_stem_job_is_404():
    r = client.post("/midi/convert", json={"stem_job_id": "nope", "stems": ["vocals"]})
    assert r.status_code == 404


def test_midi_convert_needs_audio_or_stem_job():
    assert client.post("/midi/convert", json={"model": "basic"}).status_code == 422


def test_midi_convert_reuses_a_finished_stem_job(tmp_path, monkeypatch):
    import pretty_midi
    import app.routes.midi as midi_routes
    from app.models.job import Job, JobType
    from app.utils.storage import job_store

    song, vocals = tmp_path / "song.wav", tmp_path / "song_vocals.wav"
    song.write_bytes(b"RIFF")
    vocals.write_bytes(b"RIFF")
    stems_job = Job(job_type=JobType.STEM_SEPARATION, payload={"audio_path": str(song)})
    stems_job.mark_success({"artifacts": {"vocals": str(vocals)}})
    job_store[str(stems_job.id)] = stems_job

    seen = {}

    def fake_stems(audio_path, only=None, stems=None):
        seen.update(audio=str(audio_path), only=only, stems=stems)
        out = tmp_path / "out.mid"
        pretty_midi.PrettyMIDI().write(str(out))
        return out, {"tracks": {"vocals": 1}}

    monkeypatch.setattr(midi_routes, "transcribe_stems", fake_stems)
    monkeypatch.setattr(midi_routes, "render_audio", lambda _p: None)

    assert client.post("/midi/convert", json={"stem_job_id": str(stems_job.id), "stems": ["bass"]}).status_code == 400
    r = client.post("/midi/convert", json={"stem_job_id": str(stems_job.id), "stems": ["vocals"]})
    assert r.status_code == 200 and r.json()["payload"]["model"] == "stems"
    job = client.get(f"/midi/jobs/{r.json()['id']}").json()
    assert job["status"] == "done", job
    assert seen == {"audio": str(song), "only": ["vocals"], "stems": {"vocals": str(vocals)}}


def test_enrich_files_merges_several_exports_into_one_csv():
    import time
    from pathlib import Path

    import pandas as pd

    fx = Path(__file__).parent / "fixtures" / "exports"
    names = ["exportify.csv", "StreamingHistory_music_0.json", "YourLibrary.json", "Playlist1.json"]
    r = client.post(
        "/csv/enrich-files",
        files=[("files", (n, (fx / n).read_bytes())) for n in names],
        data={"lookup": "false"},
    )
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]
    for _ in range(50):
        job = client.get(f"/csv/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.1)
    assert job["status"] == "done", job
    m = job["result"]["metrics"]
    assert [f["type"] for f in m["files"]][2].startswith("Spotify liked")
    assert m["duplicates_merged"] > 0
    df = pd.read_csv(job["result"]["library_csv"])
    assert (df["title"] == "Here").sum() == 1 and "Snooze" in set(df["title"])


def test_enrich_files_can_return_one_csv_per_input():
    import time
    from pathlib import Path

    import pandas as pd

    fx = Path(__file__).parent / "fixtures" / "exports"
    names = ["exportify.csv", "StreamingHistory_music_0.json", "YourLibrary.json"]
    r = client.post(
        "/csv/enrich-files",
        files=[("files", (n, (fx / n).read_bytes())) for n in names],
        data={"lookup": "false", "output": "separate"},
    )
    assert r.status_code == 200, r.text
    for _ in range(50):
        job = client.get(f"/csv/jobs/{r.json()['id']}").json()
        if job["status"] != "running":
            break
        time.sleep(0.1)
    assert job["status"] == "done", job
    outs = job["result"]["metrics"]["outputs"]
    assert len(outs) == 3 and all(o["csv"] for o in outs)
    assert job["result"]["artifacts"]["zip"].endswith(".zip")
    history = pd.read_csv(outs[1]["csv"])
    here = history[history["title"] == "Here"].iloc[0]
    assert here["play_count"] == 2  # this file's own plays, not summed with others
    assert here["bpm"] == 120.2  # details from the other files (and online) are filled in
