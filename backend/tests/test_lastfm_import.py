import time
import urllib.parse

import pytest

from app.core import genres, lastfm_import


def _fake_api(pages_recent=1):
    """A tiny stand-in for Last.fm's API, keyed by method."""
    def answer(url, timeout=15):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        m, page = q["method"], int(q.get("page", 1))
        if q["user"] == "nobody":
            return {"error": 6, "message": "User not found"}
        if m == "user.getinfo":
            return {"user": {"name": "Ann", "playcount": "1234", "registered": {"unixtime": "1500000000"}, "url": "u"}}
        if m == "user.gettoptracks":
            return {"toptracks": {"track": [
                {"name": "Here", "playcount": "50", "artist": {"name": "Alessia Cara"}, "url": "a"},
                {"name": "Tennessee", "playcount": "20", "artist": {"name": "Allan Rayman"}, "url": "b"},
            ], "@attr": {"totalPages": "1"}}}
        if m == "user.getlovedtracks":
            # A single loved track comes back as an object, not a list
            return {"lovedtracks": {"track": {"name": "Tennessee", "artist": {"name": "Allan Rayman"},
                                              "date": {"uts": "1600000000"}}, "@attr": {"totalPages": "1"}}}
        if m == "user.getrecenttracks":
            base = 1700000000 - (page - 1) * 10_000
            return {"recenttracks": {"track": [
                {"name": "Now", "artist": {"#text": "Someone"}, "@attr": {"nowplaying": "true"}},
                {"name": "Here", "artist": {"#text": "Alessia Cara"}, "album": {"#text": "Know-It-All"}, "date": {"uts": str(base)}},
                {"name": "Tennessee", "artist": {"#text": "Allan Rayman"}, "date": {"uts": str(base - 200)}},
                {"name": "Here", "artist": {"#text": "Alessia Cara"}, "album": {"#text": "Know-It-All"}, "date": {"uts": str(base - 400)}},
                {"name": "Tennessee", "artist": {"#text": "Allan Rayman"}, "date": {"uts": str(base - 600)}},
                {"name": "Only Recent", "artist": {"#text": "New Artist"}, "date": {"uts": str(base - 5000)}},
            ], "@attr": {"totalPages": str(pages_recent)}}}
        raise AssertionError(m)
    return answer


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("LASTFM_API_KEY", "x")
    monkeypatch.setattr(genres, "_get", _fake_api())


def test_fetch_builds_one_row_per_song(fake):
    df, summary = lastfm_import.fetch("ann")
    by = {t: r for t, r in zip(df["title"], df.to_dict("records"))}
    assert set(by) == {"Here", "Tennessee", "Only Recent"}  # now-playing left out
    # All-time play count from top tracks, not added to the recent plays
    assert by["Here"]["play_count"] == 50
    assert by["Only Recent"]["play_count"] == 1
    assert by["Tennessee"]["liked"] is True
    assert by["Here"]["album"] == "Know-It-All"
    assert by["Here"]["last_played"] == "2023-11-14"
    assert "allan rayman" in str(by["Here"]["played_with"])  # back to back twice
    assert summary["user"] == "Ann" and summary["top_tracks"] == 2 and summary["recent_scrobbles"] == 5
    assert summary["whole_history"] is True


def test_partial_history_has_no_first_played(monkeypatch):
    monkeypatch.setenv("LASTFM_API_KEY", "x")
    monkeypatch.setattr(genres, "_get", _fake_api(pages_recent=50))
    df, summary = lastfm_import.fetch("ann", recent_pages=2)
    assert summary["whole_history"] is False
    assert df["first_played"].isna().all()


def test_unknown_user_and_missing_key(fake, monkeypatch):
    with pytest.raises(lastfm_import.LastfmError, match="no Last.fm user"):
        lastfm_import.fetch("nobody")
    monkeypatch.delenv("LASTFM_API_KEY")
    with pytest.raises(lastfm_import.LastfmError, match="LASTFM_API_KEY"):
        lastfm_import.fetch("ann")


def test_import_route_runs_in_background(fake, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core import library_import
    from app.main import app

    monkeypatch.setattr(library_import, "enrich", lambda df, limit, progress: (df.assign(genre="Pop"), len(df)))
    c = TestClient(app)
    assert c.get("/csv/lastfm/status").json() == {"enabled": True}
    job = c.post("/csv/import-lastfm", json={"username": "ann"}).json()
    for _ in range(50):
        job = c.get(f"/csv/jobs/{job['id']}").json()
        if job["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    m = job["result"]["metrics"]
    assert m["songs"] == 3 and m["lastfm"]["user"] == "Ann" and m["coverage_after"]["genre"] == 1.0
    assert job["result"]["library_csv"].endswith(".csv")


def test_import_route_says_when_no_key(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    r = TestClient(app).post("/csv/import-lastfm", json={"username": "ann"})
    assert r.status_code == 503 and "LASTFM_API_KEY" in r.json()["detail"]


def test_stray_quotes_in_the_key_are_ignored(monkeypatch):
    from app.core import config

    monkeypatch.setenv("LASTFM_API_KEY", ' "abc123" ')  # what a sloppy compose line can pass in
    config._load_dotenv()
    assert lastfm_import.api_key() == "abc123" and lastfm_import.enabled()
