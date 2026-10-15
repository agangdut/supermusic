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


def test_shares_get_a_picture_and_showcase_stats():
    share = client.post("/map/share", json={"map": _sample_map(), "title": "Pretty", "listed": True, "sample": True}).json()
    assert share["picture"] is True
    sc = share["showcase"]
    assert sc["songs"] == share["songs"] and sc["clusters"] >= 2 and sc["galaxies"]
    assert sc["top_genres"] and sc["top_artists"]
    r = client.get(f"/map/shared/{share['id']}/picture.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:4] == b"\x89PNG"


def test_older_shares_get_their_picture_when_listed():
    import json
    from app.core import map_share

    share = client.post("/map/share", json={"map": _sample_map(), "title": "Old", "listed": True, "sample": True}).json()
    folder = map_share.share_dir() / share["id"]
    meta = json.loads((folder / "meta.json").read_text())
    meta.pop("showcase"), meta.pop("picture")
    (folder / "meta.json").write_text(json.dumps(meta))
    (folder / "picture.png").unlink()
    listed = {m["id"]: m for m in client.get("/map/shared").json()["maps"]}
    assert listed[share["id"]]["showcase"]["songs"] == share["songs"]
    assert (folder / "picture.png").is_file()


def test_upvotes_one_per_listener_and_top_sort():
    a = client.post("/map/share", json={"map": _sample_map(), "title": "A", "listed": True, "sample": True}).json()
    b = client.post("/map/share", json={"map": _sample_map(), "title": "B", "listed": True, "sample": True}).json()
    url = f"/map/shared/{b['id']}/vote"
    assert client.post(url, json={"up": True}).status_code == 400  # nobody to count
    me = {"X-Listener-Id": "listener-one-123"}
    assert client.post(url, json={"up": True}, headers=me).json() == {"votes": 1, "voted": True}
    assert client.post(url, json={"up": True}, headers=me).json()["votes"] == 1  # twice counts once
    client.post(url, json={"up": True}, headers={"X-Listener-Id": "listener-two-456"})
    top = client.get("/map/shared", params={"sort": "top"}, headers=me).json()["maps"]
    assert top[0]["id"] == b["id"] and top[0]["votes"] == 2 and top[0]["voted"] is True
    assert client.get(f"/map/shared/{b['id']}", headers=me).json()["voted"] is True
    assert client.post(url, json={"up": False}, headers=me).json() == {"votes": 1, "voted": False}
    new = client.get("/map/shared", params={"sort": "new"}).json()["maps"]
    assert [m["id"] for m in new].index(b["id"]) < [m["id"] for m in new].index(a["id"])


def test_one_network_cant_stuff_votes():
    sid = client.post("/map/share", json={"map": _sample_map(), "title": "Stuffed", "sample": True}).json()["id"]
    codes = [client.post(f"/map/shared/{sid}/vote", json={"up": True}, headers={"X-Listener-Id": f"sock-puppet-{i:04d}"}).status_code
             for i in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 429


def test_votes_go_with_the_share():
    share = client.post("/map/share", json={"map": _sample_map(), "title": "Bye", "sample": True}).json()
    client.post(f"/map/shared/{share['id']}/vote", json={"up": True}, headers={"X-Listener-Id": "listener-bye-789"})
    client.post(f"/map/shared/{share['id']}/delete", json={"delete_token": share["delete_token"]})
    assert client.post(f"/map/shared/{share['id']}/vote", json={"up": True},
                       headers={"X-Listener-Id": "listener-bye-789"}).status_code == 404
