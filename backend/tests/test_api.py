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


def test_midi_convert_rejects_unknown_stem():
    r = client.post("/midi/convert", json={"source_path": "x.wav", "model": "stems", "stems": ["kazoo"]})
    assert r.status_code == 422


def test_midi_convert_from_missing_stem_job_is_404():
    r = client.post("/midi/convert", json={"stem_job_id": "nope", "stems": ["vocals"]})
    assert r.status_code == 404


def test_midi_convert_needs_audio_or_stem_job():
    assert client.post("/midi/convert", json={"model": "basic"}).status_code == 422


def test_midi_convert_reuses_a_finished_stem_job(tmp_path, monkeypatch):
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
        out.write_bytes(b"MThd")
        return out, {"tracks": {"vocals": 1}}

    monkeypatch.setattr(midi_routes, "transcribe_stems", fake_stems)
    monkeypatch.setattr(midi_routes, "render_audio", lambda _p: None)

    assert client.post("/midi/convert", json={"stem_job_id": str(stems_job.id), "stems": ["bass"]}).status_code == 400
    r = client.post("/midi/convert", json={"stem_job_id": str(stems_job.id), "stems": ["vocals"]})
    assert r.status_code == 200 and r.json()["payload"]["model"] == "stems"
    job = client.get(f"/midi/jobs/{r.json()['id']}").json()
    assert job["status"] == "done", job
    assert seen == {"audio": str(song), "only": ["vocals"], "stems": {"vocals": str(vocals)}}
