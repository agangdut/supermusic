"""What keeps the public site safe: only SuperMusic's own files can be read, results
can't be guessed, jobs wait in line and survive a restart, and limits hold."""
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.core import jobs
from app.main import app
from app.models.job import Job, JobStatus, JobType
from app.utils import storage

client = TestClient(app)


def test_requests_cant_point_at_server_files(tmp_path):
    from app.core import store

    store.connect()  # make sure the database file exists
    db = str(store.db_path())
    outside = tmp_path / "secret.wav"
    outside.write_bytes(b"x")
    for path, body in [
        ("/midi/convert", {"source_path": str(outside), "model": "basic"}),
        ("/midi/convert", {"source_path": "/etc/passwd", "model": "basic"}),
        ("/stems/separate", {"audio_path": db}),
        ("/csv/enrich", {"csv_path": "/etc/passwd"}),
        ("/map/build", {"csv_path": db}),
        ("/midi/playability", {"midi_path": "/etc/passwd"}),
        ("/batch/process", {"audio_files": [str(outside)], "operations": ["midi"]}),
    ]:
        r = client.post(path, json=body)
        assert r.status_code in (404, 422), (path, r.status_code, r.text)


def test_uploads_and_results_get_unguessable_folders():
    a = client.post("/upload/csv", files={"file": ("mine.csv", b"title,artist\nA,B\n", "text/csv")}).json()["path"]
    b = client.post("/upload/csv", files={"file": ("mine.csv", b"title,artist\nA,B\n", "text/csv")}).json()["path"]
    assert Path(a).name == Path(b).name == "mine.csv"
    assert Path(a).parent != Path(b).parent and len(Path(a).parent.name) >= 16
    saved = storage.save_bytes("Song (two hands).mid", b"m")
    assert len(Path(saved).parent.name) >= 16


def test_too_big_uploads_are_refused(monkeypatch):
    from app.routes import upload

    monkeypatch.setattr(upload, "MAX_UPLOAD_MB", 1)
    r = client.post("/upload/csv", files={"file": ("big.csv", b"x" * (1024 * 1024 + 10), "text/csv")})
    assert r.status_code == 413


def test_websocket_lists_no_ones_jobs():
    job = Job(job_type=JobType.STEM_SEPARATION)
    storage.job_store[job.id] = job
    with client.websocket_connect("/ws/jobs") as ws:
        assert ws.receive_json() == {"type": "initial_jobs", "jobs": {}}
        ws.send_json({"type": "subscribe", "job_id": job.id})
        assert ws.receive_json()["job_id"] == job.id


def test_finished_jobs_survive_a_restart_and_running_ones_say_so():
    done = Job(job_type=JobType.STEM_SEPARATION)
    done.mark_success({"artifacts": {}}, "ok")
    running = Job(job_type=JobType.MIDI_CONVERSION)
    running.mark_running("working")
    dict.clear(storage.job_store)  # what a restart does to memory
    assert storage.job_store.get(done.id).status == JobStatus.done
    back = storage.job_store.get(running.id)
    assert back.status == JobStatus.error and "restarted" in back.error_detail
    assert client.get(f"/midi/jobs/{running.id}").json()["status"] == "error"


def test_heavy_jobs_wait_in_line(monkeypatch, user_dir):
    from app.routes import stems as stems_routes

    started = []

    def slow(audio_path, out_dir=None, model="htdemucs"):
        started.append(time.time())
        time.sleep(0.3)
        return {}

    monkeypatch.setattr(stems_routes, "run_separation", slow)
    song = user_dir / "song.wav"
    song.write_bytes(b"x")
    ids = [client.post("/stems/separate", json={"audio_path": str(song)}).json()["id"] for _ in range(2)]
    for _ in range(60):
        states = [client.get(f"/stems/jobs/{i}").json()["status"] for i in ids]
        if all(s in ("done", "error") for s in states):
            break
        time.sleep(0.1)
    assert states == ["done", "done"]
    assert len(started) == 2 and started[1] - started[0] >= 0.25  # one at a time


def test_limits_per_person(monkeypatch, user_dir):
    monkeypatch.setenv("SM_RATE_LIMITS", "1")
    monkeypatch.setattr(jobs, "PER_HOUR", 2)
    monkeypatch.setattr(jobs, "MAX_ACTIVE", 0)
    jobs._started.clear()
    song = user_dir / "song.wav"
    song.write_bytes(b"x")
    h = {"X-Listener-Id": "limit-test"}
    codes = [client.post("/stems/separate", json={"audio_path": str(song)}, headers=h).status_code for _ in range(3)]
    assert codes[:2] == [200, 200] and codes[2] == 429
    jobs._started.clear()


def test_login_can_be_required_for_jobs(monkeypatch, user_dir):
    monkeypatch.setenv("SM_REQUIRE_LOGIN_FOR_JOBS", "1")
    song = user_dir / "song.wav"
    song.write_bytes(b"x")
    r = client.post("/stems/separate", json={"audio_path": str(song)})
    assert r.status_code == 401 and "Sign in" in r.json()["detail"]


def test_updates_wait_for_running_jobs(monkeypatch, tmp_path, user_dir):
    import os

    flag = tmp_path / "updating"
    monkeypatch.setattr(jobs, "_updating_file", lambda: flag)
    dict.clear(storage.job_store)
    assert client.get("/healthz/jobs").json() == {"busy": 0, "updating": False}

    running = Job(job_type=JobType.STEM_SEPARATION)
    running.mark_running("working")
    storage.put_job(running)
    assert client.get("/healthz/jobs").json()["busy"] == 1

    # deploy/update.sh pauses new jobs while it waits; the running one carries on
    flag.touch()
    song = user_dir / "song.wav"
    song.write_bytes(b"x")
    r = client.post("/stems/separate", json={"audio_path": str(song)})
    assert r.status_code == 503 and "updating" in r.json()["detail"]
    assert "updating" in client.post("/csv/import-lastfm", json={"username": "x"}).json()["detail"]
    assert client.get("/healthz/jobs").json() == {"busy": 1, "updating": True}

    running.mark_success({"artifacts": {}}, "ok")
    assert client.get("/healthz/jobs").json()["busy"] == 0

    # A pause left behind by an update that crashed runs out by itself
    old = time.time() - jobs.UPDATING_EXPIRES_S - 60
    os.utime(flag, (old, old))
    assert not jobs.updating()


def test_downloads_only_from_known_sites(monkeypatch):
    r = client.post("/tracks/download", json={"url": "http://169.254.169.254/latest/meta-data"})
    assert r.status_code == 400
    monkeypatch.setenv("SM_ENABLE_DOWNLOADS", "0")
    assert client.post("/tracks/download", json={"url": "https://youtu.be/abc"}).status_code == 403


def test_cleanup_deletes_old_results_but_keeps_libraries_in_use(monkeypatch):
    import os

    from app.core import cleanup

    old = Path(storage.save_bytes("Old song.mid", b"m"))
    new = Path(storage.save_bytes("New song.mid", b"m"))
    kept = Path(storage.save_bytes("My library.csv", b"title\n"))
    week_ago = time.time() - 8 * 86400
    for p in (old, kept):
        os.utime(p.parent, (week_ago, week_ago))
    monkeypatch.setattr(cleanup, "_in_use", lambda: {kept.resolve()})
    cleanup.sweep()
    assert not old.exists() and new.exists() and kept.exists()


def test_delete_account_removes_it():
    r = client.post("/auth/register", json={"username": "leaving", "password": "longpassword1"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.post("/auth/me/delete", json={"password": "wrong-password"}, headers=h).status_code == 401
    assert client.post("/auth/me/delete", json={"password": "longpassword1"}, headers=h).json()["deleted"] is True
    assert client.post("/auth/login", json={"username": "leaving", "password": "longpassword1"}).status_code == 401
    assert client.get("/auth/me", headers=h).status_code == 404


def test_production_refuses_the_default_secret(monkeypatch):
    import importlib

    import app.middleware.auth as auth

    monkeypatch.setenv("SM_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "change-me-in-production")
    try:
        importlib.reload(auth)
        raise AssertionError("should have refused to start")
    except RuntimeError:
        pass
    finally:
        monkeypatch.delenv("SM_ENV")
        monkeypatch.delenv("JWT_SECRET_KEY")
        importlib.reload(auth)


def test_stems_come_back_as_mp3_and_leave_no_work_files(monkeypatch, user_dir):
    """The stem player downloads every stem: MP3 keeps that ~4x smaller than WAV."""
    import shutil as sh
    import subprocess

    if not sh.which("ffmpeg"):
        pytest.skip("needs ffmpeg")
    from app.routes import stems as stems_routes

    work_dirs = []

    def fake(audio_path, out_dir=None, model="htdemucs"):
        work_dirs.append(out_dir)
        out = {}
        for name in ("vocals", "bass"):
            wav = out_dir / model / "song" / f"{name}.wav"
            wav.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=d=1", str(wav)], check=True)
            out[name] = str(wav)
        return out

    monkeypatch.setattr(stems_routes, "run_separation", fake)
    song = user_dir / "song.wav"
    song.write_bytes(b"x")
    job_id = client.post("/stems/separate", json={"audio_path": str(song)}).json()["id"]
    for _ in range(100):
        job = client.get(f"/stems/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert job["status"] == "done", job.get("error_detail")
    arts = job["result"]["artifacts"]
    assert set(arts) == {"vocals", "bass"}
    assert all(p.endswith(".mp3") and Path(p).read_bytes()[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3") for p in arts.values())
    assert work_dirs and work_dirs[0] is not None and not work_dirs[0].exists()


def test_unreadable_audio_is_refused_at_upload():
    """A cut-off download or an error page saved as .wav fails here, not minutes later in a job."""
    import shutil as sh

    if not sh.which("ffprobe"):
        pytest.skip("needs ffprobe")
    r = client.post("/upload/audio", files={"file": ("stem (other).wav", b'{"detail":"Not Found"}', "audio/wav")})
    assert r.status_code == 400 and "damaged" in r.json()["detail"]


def test_stems_are_never_bigger_files_than_the_song(tmp_path):
    import shutil as sh
    import subprocess

    if not sh.which("ffmpeg"):
        pytest.skip("needs ffmpeg")
    from app.routes.stems import stem_bitrate

    def song(kbps):
        p = tmp_path / f"s{kbps}.mp3"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=d=2", "-b:a", f"{kbps}k", str(p)], check=True)
        return p

    assert stem_bitrate(song(128)) == "128k"
    assert stem_bitrate(song(320)) == "192k"   # capped
    assert stem_bitrate(song(64)) == "96k"     # not below the floor
    assert stem_bitrate(tmp_path / "missing.mp3") == "192k"
