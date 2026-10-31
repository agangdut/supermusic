"""Accounts, profiles, follows, the feed, share cards, compare (blend), the atlas, the quiz,
the digest and the leaderboards."""
import io
import uuid

import pandas as pd
from fastapi.testclient import TestClient

from app.core import atlas
from app.main import app
from app.routes.map import SAMPLE_CSV

client = TestClient(app)


def _user(name=None):
    name = name or f"u{uuid.uuid4().hex[:8]}"
    r = client.post("/auth/register", json={"username": name, "password": "password123", "display_name": name.upper()})
    assert r.status_code == 200, r.text
    return name, {"Authorization": f"Bearer {r.json()['access_token']}"}


def _sample_map():
    return client.post("/map/build", json={"sample": True}).json()


def _upload(df):
    buf = io.BytesIO(df.to_csv(index=False).encode())
    r = client.post("/upload/csv", files={"file": ("mine.csv", buf, "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()["path"]


def test_register_login_and_edit_profile():
    name, auth = _user()
    assert client.post("/auth/register", json={"username": name, "password": "password123"}).status_code == 400
    assert client.post("/auth/register", json={"username": "has space", "password": "password123"}).status_code == 400
    r = client.post("/auth/login", json={"username": name.upper(), "password": "password123"})  # any case
    assert r.status_code == 200 and r.json()["user"]["username"] == name
    assert client.post("/auth/login", json={"username": name, "password": "nope-nope"}).status_code == 401

    me = client.patch("/auth/me", json={"display_name": "DJ Test", "bio": "I like jazz", "is_artist": True}, headers=auth).json()
    assert me["display_name"] == "DJ Test" and me["bio"] == "I like jazz" and me["is_artist"]
    p = client.get(f"/users/{name}", headers=auth).json()
    assert p["is_me"] and p["display_name"] == "DJ Test" and p["followers"] == 0
    assert client.get("/users/nobody-here-xyz").status_code == 404
    assert client.patch("/auth/me", json={"bio": "x"}).status_code == 401


def test_shares_go_on_the_profile_and_into_followers_feeds():
    alice, a_auth = _user()
    bob, b_auth = _user()
    assert client.post(f"/users/{alice}/follow", json={"on": True}, headers=b_auth).json()["followers"] == 1
    assert client.post(f"/users/{bob}/follow", json={"on": True}, headers=b_auth).status_code == 400  # not yourself

    r = client.post("/map/share", json={"map": _sample_map(), "title": "Alice's map", "listed": True, "sample": True},
                    headers=a_auth)
    share = r.json()
    assert share["owner"] == alice and share["by"] == alice.upper()  # display name by default

    prof = client.get(f"/users/{alice}").json()
    assert [m["id"] for m in prof["maps"]] == [share["id"]]
    assert client.get(f"/users/{alice}/followers").json()["users"][0]["username"] == bob

    feed = client.get("/feed", headers=b_auth).json()
    assert any(e["kind"] == "shared_map" and e["data"]["id"] == share["id"] for e in feed["items"])
    # Alice hears about Bob's follow and upvote
    client.post(f"/map/shared/{share['id']}/vote", json={"up": True}, headers=b_auth)
    kinds = {e["kind"] for e in client.get("/feed", headers=a_auth).json()["items"]}
    assert {"followed", "upvoted"} <= kinds

    # The owner can unlist and delete without the browser's token
    assert client.post(f"/map/shared/{share['id']}/listed", json={"listed": False}, headers=b_auth).status_code == 403
    assert client.post(f"/map/shared/{share['id']}/listed", json={"listed": False}, headers=a_auth).status_code == 200
    assert client.post(f"/map/shared/{share['id']}/delete", json={}, headers=a_auth).status_code == 200


def test_claiming_shares_made_before_signing_in():
    s = client.post("/map/share", json={"map": _sample_map(), "title": "Anon", "sample": True}).json()
    name, auth = _user()
    bad = client.post("/auth/claim-shares", json={"shares": [{"id": s["id"], "delete_token": "wrong-token"}]}, headers=auth)
    assert bad.json()["claimed"] == []
    ok = client.post("/auth/claim-shares", json={"shares": [{"id": s["id"], "delete_token": s["delete_token"]}]}, headers=auth)
    assert ok.json()["claimed"] == [s["id"]]
    assert s["id"] in [m["id"] for m in client.get(f"/users/{name}", headers=auth).json()["maps"]]


def test_share_card_is_a_png():
    s = client.post("/map/share", json={"map": _sample_map(), "title": "A very long title for a card test", "sample": True}).json()
    r = client.get(f"/map/shared/{s['id']}/card.png")
    assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert client.get("/map/shared/zzzzzzzz/card.png").status_code == 404


def test_blend_tags_whose_songs_they_are():
    sample = pd.read_csv(SAMPLE_CSV)
    half = len(sample) // 2
    mine = sample.iloc[: half + 5]
    theirs = sample.iloc[half - 5:]
    share = client.post("/map/share", json={"map": _sample_map(), "title": "Theirs", "sample": True}).json()
    # Point the share at a library with only "their" half
    from app.core import map_share

    theirs.to_csv(map_share.library_path(share["id"]), index=False)

    r = client.post("/map/blend", json={"mine": {"csv_path": _upload(mine)}, "theirs": {"share_id": share["id"]}})
    assert r.status_code == 200, r.text
    m = r.json()
    who = {t["who"] for t in m["tracks"]}
    assert who == {"you", "them", "both"}
    b = m["blend"]
    assert b["counts"]["both"] == 10 and b["counts"]["you"] + b["counts"]["both"] == len(mine.drop_duplicates(["title", "artist"]))
    assert 0 <= b["match"] <= 100 and b["theirs"]["title"] == "Theirs"
    assert all(g["kind"] in ("shared", "yours", "theirs") for g in b["galaxies"])
    assert not any("plays" in t for t in m["tracks"])  # nobody's play counts in a blend


def test_atlas_pins_and_mine():
    client.post("/map/share", json={"map": _sample_map(), "title": "For the atlas", "listed": True, "sample": True})
    a = atlas.build()
    assert a["tracks"] and all("song_key" in t and t["listeners"] >= 1 for t in a["tracks"])
    got = client.get("/atlas").json()
    assert got["meta"]["source"] == "community atlas" and "artist_tracks" in got

    ids = client.post("/atlas/mine", json={"sample": True}).json()["ids"]
    assert len(ids) > 0

    key = a["tracks"][0]["song_key"]
    h = {"X-Listener-Id": "pinner-123456"}
    pin = client.post("/atlas/pins", json={"song_key": key, "text": "  great   bassline "}, headers=h).json()
    assert pin["text"] == "great bassline"
    song = client.get("/atlas/song", params={"song_key": key}).json()
    assert song["pins"][0]["text"] == "great bassline" and song["maps"]
    assert client.delete(f"/atlas/pins/{pin['id']}", headers={"X-Listener-Id": "someone-else-1"}).status_code == 403
    assert client.delete(f"/atlas/pins/{pin['id']}", headers=h).status_code == 200


def _wait_for_atlas_builds(timeout=60):
    import time
    end = time.time() + timeout
    while atlas._building[0] and time.time() < end:
        time.sleep(0.1)
    assert not atlas._building[0]


def test_atlas_rebuilds_when_a_map_is_shared_and_is_served_from_memory(monkeypatch):
    import gzip
    import json

    _wait_for_atlas_builds()
    atlas.build()
    before = client.get("/atlas").json()["meta"]["maps"]
    r = client.post("/map/share", json={"map": _sample_map(), "title": "Rebuild me", "listed": True, "sample": True}).json()
    _wait_for_atlas_builds()
    assert client.get("/atlas").json()["meta"]["maps"] == before + 1  # no manual build needed

    # Between changes the answer comes from memory: no reading or re-encoding the file
    loads = []
    real = atlas._load
    monkeypatch.setattr(atlas, "_load", lambda name: loads.append(name) or real(name))
    a = client.get("/atlas", headers={"Accept-Encoding": "gzip"})
    b = client.get("/atlas", headers={"Accept-Encoding": "identity"})
    assert loads == []
    assert a.headers.get("content-encoding") == "gzip" and "content-encoding" not in b.headers
    assert a.json() == b.json() and "artist_tracks" in b.json()

    # The browser's copy is reused while nothing changed
    again = client.get("/atlas", headers={"Accept-Encoding": "gzip", "If-None-Match": a.headers["etag"]})
    assert again.status_code == 304 and not again.content

    # Unlisting (here: deleting) a map rebuilds it again
    assert client.post(f"/map/shared/{r['id']}/delete", json={"delete_token": r["delete_token"]}).status_code == 200
    _wait_for_atlas_builds()
    monkeypatch.setattr(atlas, "_load", real)
    assert client.get("/atlas").json()["meta"]["maps"] == before


def test_quiz_scores_are_counted_on_the_server():
    client.post("/map/share", json={"map": _sample_map(), "title": "Quiz map", "listed": True, "sample": True})
    atlas.build()
    h = {"X-Listener-Id": f"quizzer-{uuid.uuid4().hex[:8]}"}
    right = 0
    for _ in range(10):
        q = client.get("/games/quiz", headers=h).json()
        assert q["kind"] in ("year", "artist", "album", "genre", "first") and len(q["options"]) == 4 and "answer" not in q
        if q["kind"] == "year":
            assert "year" not in (q.get("song") or {})  # the card mustn't give the answer away
        res = client.post("/games/quiz/answer", json={"id": q["id"], "choice": q["options"][0]["id"]}, headers=h).json()
        right += res["correct"]
        # An answered question can't be answered again
        assert client.post("/games/quiz/answer", json={"id": q["id"], "choice": "x"}, headers=h).status_code == 410
    assert res["done"] and res["score"] == right
    assert client.post("/games/quiz/finish", json={"name": "Quizzer"}, headers=h).json()["score"] == right
    assert any(r["name"] == "Quizzer" for r in client.get("/leaderboards").json()["quiz"])


def test_digest_and_leaderboards():
    name, auth = _user()
    assert client.put("/me/library", json={"csv_path": "/etc/passwd"}, headers=auth).status_code == 400
    assert client.put("/me/library", json={"sample": True, "title": "Sample"}, headers=auth).status_code == 200
    d = client.get("/digest", headers=auth).json()
    assert d["has_library"] and d["week"].startswith("Week of") and len(d["rediscover"]) > 0
    assert d["upvotes"] == 0 and d["new_followers"] == 0

    client.post("/map/radio/played", json={"station": "cluster:1", "label": "Andromeda radio"},
                headers={"X-Listener-Id": "radio-fan-1234"})
    lb = client.get("/leaderboards").json()
    assert set(lb) == {"maps", "contributors", "radio", "quiz", "checkers"}
    assert any(r["station"] == "cluster:1" for r in lb["radio"])


def test_reputation_counts_agreed_fixes():
    a, a_auth = _user()
    b, b_auth = _user()
    song = {"artist": f"Rep Artist {a}", "title": "Rep Song", "field": "bpm"}
    client.post("/community/vote", json={**song, "value": 120}, headers={**a_auth, "X-Forwarded-For": "10.0.0.1"})
    client.post("/community/vote", json={**song, "value": 121}, headers={**b_auth, "X-Forwarded-For": "10.0.0.2"})
    rep = client.get(f"/users/{a}").json()["reputation"]
    assert rep["agreed"] == 1 and rep["first"] == 1 and rep["points"] == 15  # 10 agreed + 5 first; unagreed fixes earn nothing
    assert any(e["kind"] == "fix_agreed" for e in client.get("/feed", headers=a_auth).json()["items"])
