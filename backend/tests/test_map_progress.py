import time

import pandas as pd
from fastapi.testclient import TestClient

from app.core import library_import
from app.main import app
from app.routes import map as map_routes

client = TestClient(app)

CSV = "title,artist\n" + "\n".join(f"Song {i},Artist {i % 7}" for i in range(40))


def _run(monkeypatch, fake_lookup, enrich=True):
    monkeypatch.setattr(library_import, "lookup", fake_lookup)
    monkeypatch.setattr(library_import, "is_cached", lambda a, t: t.endswith(("0", "2", "4")))
    r = client.post("/map/import", files={"files": ("lib.csv", CSV, "text/csv")}, data={"enrich": str(enrich).lower()})
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]
    seen = []
    for _ in range(600):
        j = client.get(f"/map/import/{job_id}").json()
        seen.append(j)
        if j["status"] != "running":
            break
        time.sleep(0.05)
    return seen


def test_import_reports_steps_counts_and_time_left(monkeypatch):
    def fake_lookup(artist, title, analyse=True):
        time.sleep(0.01)
        n = int(title.split()[-1])
        if n % 5 == 0:
            return {}
        return {"genre": "Pop" if n % 2 else "Rock", "bpm": 90 + n, "deezer_id": n}

    seen = _run(monkeypatch, fake_lookup)
    final = seen[-1]
    assert final["status"] == "done" and final["progress"] == 100 and final["eta_s"] is None
    assert [s["state"] for s in final["steps"]] == ["done", "done", "done"]
    lk = final["lookup"]
    assert lk["todo"] == 40 and lk["done"] == 40 and lk["cached"] == 12
    assert lk["found"] == 32 and lk["not_found"] == 8 and lk["failed"] == 0
    progress = [j["progress"] for j in seen]
    assert progress == sorted(progress), "the bar never goes backwards"
    running = [j for j in seen if j["status"] == "running" and j["eta_s"] is not None]
    assert running and all(j["eta_s"] >= 0 for j in running)
    assert "result" in final and final["result"]["meta"]["count"] == 40


def test_unreachable_services_stop_early_with_a_warning(monkeypatch):
    calls = []

    def offline(artist, title, analyse=True):
        calls.append(title)
        return {"error": "network down"}

    final = _run(monkeypatch, offline)[-1]
    assert len(calls) == 8  # gave up instead of trying all 40
    assert final["warning"] and "reach" in final["warning"]
    assert final["lookup"]["failed"] == 8 and final["lookup"]["skipped"] == 32


def test_lost_import_says_so():
    r = client.get("/map/import/nope")
    assert r.status_code == 404 and "import again" in r.json()["detail"]


def test_time_left_follows_measured_speed():
    job = map_routes.ImportJob([{"file": "x", "type": "csv", "songs": 100}], enrich=True)
    job.step = "lookup"
    job.on_start({"needed": 100, "todo": 100, "cached": 0})
    for _ in range(10):
        job.on_song({"cached": False, "found": True, "error": False, "seconds": 0.5})
    left = job.time_left()
    from app.core.music_map import estimate_build_seconds
    assert abs(left - (90 * 0.5 + estimate_build_seconds(100))) < 0.01


def test_build_estimate_grows_with_library():
    from app.core.music_map import estimate_build_seconds
    assert estimate_build_seconds(3000) > estimate_build_seconds(1500) > estimate_build_seconds(500)
    assert client.get("/map/estimate", params={"tracks": 1500}).json()["seconds"] > 0
