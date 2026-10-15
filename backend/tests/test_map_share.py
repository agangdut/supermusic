from fastapi.testclient import TestClient

from app.core import listen_links
from app.main import app

client = TestClient(app)


def _sample_map():
    r = client.post("/map/build", json={"sample": True})
    assert r.status_code == 200
    return r.json()


def test_share_round_trip_and_visitors_can_use_the_library():
    m = _sample_map()
    r = client.post("/map/share", json={"map": m, "title": "My taste", "by": "A", "listed": True, "sample": True,
                                        "weights": {"key": 1.5}})
    assert r.status_code == 200, r.text
    share = r.json()
    assert share["delete_token"] and share["has_library"] and share["songs"] == len(m["tracks"])
    assert "token_sha256" not in share

    got = client.get(f"/map/shared/{share['id']}").json()
    assert got["title"] == "My taste" and got["by"] == "A"
    assert len(got["map"]["tracks"]) == len(m["tracks"])
    assert got["map"]["meta"]["weights"] == {"key": 1.5}
    assert "delete_token" not in got and "token_sha256" not in got

    assert share["id"] in [s["id"] for s in client.get("/map/shared").json()["maps"]]

    # Remap and "songs you may like" work from the share's own copy of the songs
    assert client.post("/map/build", json={"share_id": share["id"]}).status_code == 200
    assert client.post("/map/like", json={"share_id": share["id"], "id": 0, "limit": 3}).status_code == 200


def test_unlisted_share_stays_off_the_public_list():
    r = client.post("/map/share", json={"map": _sample_map(), "title": "Secret", "sample": True})
    sid = r.json()["id"]
    assert sid not in [s["id"] for s in client.get("/map/shared").json()["maps"]]
    assert client.get(f"/map/shared/{sid}").status_code == 200


def test_hiding_listening_data_strips_plays_everywhere():
    m = _sample_map()
    assert any("plays" in t for t in m["tracks"])  # the sample has play counts
    r = client.post("/map/share", json={"map": m, "title": "No plays", "sample": True, "include_listening": False})
    sid = r.json()["id"]
    got = client.get(f"/map/shared/{sid}").json()["map"]
    assert not any("plays" in t or "engagement" in t for t in got["tracks"])
    assert got["recommendations"] == [] and got["insights"] == [] and "stats" not in got
    assert not any("lift" in c for c in got["clusters"])
    # The library copy has no play column either, so a Remap can't bring them back
    remap = client.post("/map/build", json={"share_id": sid}).json()
    assert remap["meta"]["has_listening_data"] is False


def test_unsafe_links_are_dropped():
    m = _sample_map()
    m["tracks"][0]["spotify_url"] = "javascript:alert(1)"
    m["tracks"][1]["youtube_url"] = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    sid = client.post("/map/share", json={"map": m, "title": "Links"}).json()["id"]
    tracks = client.get(f"/map/shared/{sid}").json()["map"]["tracks"]
    assert "spotify_url" not in tracks[0]
    assert tracks[1]["youtube_url"].endswith("dQw4w9WgXcQ")


def test_only_supermusic_files_can_be_shared(tmp_path):
    outside = tmp_path / "other.csv"
    outside.write_text("title,artist\nPrivate,Someone\n")
    r = client.post("/map/share", json={"map": _sample_map(), "title": "Sneaky", "csv_path": str(outside)})
    assert r.status_code == 200
    assert r.json()["has_library"] is False


def test_delete_needs_the_token():
    share = client.post("/map/share", json={"map": _sample_map(), "title": "Temp", "sample": True}).json()
    url = f"/map/shared/{share['id']}/delete"
    assert client.post(url, json={"delete_token": "wrong-token-123"}).status_code == 403
    assert client.post(url, json={"delete_token": share["delete_token"]}).status_code == 200
    assert client.get(f"/map/shared/{share['id']}").status_code == 404


def test_bad_ids_and_bad_maps():
    assert client.get("/map/shared/..%2F..%2Fetc").status_code == 404
    assert client.get("/map/shared/nope").status_code == 404
    assert client.post("/map/share", json={"map": {"tracks": []}, "title": "Empty"}).status_code == 400


def test_preview_uses_deezer(monkeypatch):
    calls = []

    def fake_get(url):
        calls.append(url)
        if "/search" in url:
            return {"data": [{"id": 42, "title": "Song", "artist": {"name": "Band"}}]}
        return {"id": 42, "preview": "https://cdn.example/42.mp3", "link": "https://www.deezer.com/track/42"}

    monkeypatch.setattr(listen_links.library_import, "_get", fake_get)
    r = client.get("/map/preview", params={"artist": "Band", "title": "Song"})
    assert r.json()["preview"] == "https://cdn.example/42.mp3"
    n = len(calls)
    client.get("/map/preview", params={"artist": "Band", "title": "Song"})
    assert len(calls) == n + 1  # the id is cached; only the fresh preview link is fetched


def test_youtube_ids_prefer_the_csv_link(monkeypatch):
    monkeypatch.setattr(listen_links, "_yt_search", lambda q: "abcdefghijk")
    r = client.post("/map/youtube-ids", json={"songs": [
        {"title": "A", "youtube_url": "https://youtu.be/dQw4w9WgXcQ"},
        {"title": "B", "artist": "C"},
    ]})
    assert r.json()["ids"] == ["dQw4w9WgXcQ", "abcdefghijk"]
