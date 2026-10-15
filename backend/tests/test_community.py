import pandas as pd
from fastapi.testclient import TestClient

from app.core import community
from app.main import app

client = TestClient(app)

SAMPLE = pd.read_csv("app/sample_data/sample_library.csv")
TITLE, ARTIST = str(SAMPLE["title"][0]), str(SAMPLE["artist"][0])


def _vote(listener, field, value, ip="1.1.1.1", title=TITLE):
    return client.post("/community/vote", json={"artist": ARTIST, "title": title, "field": field, "value": value},
                       headers={"X-Listener-Id": listener, "X-Forwarded-For": ip})


def test_agreement_rules():
    assert community.agree("bpm", [90]) is None                       # one listener is not enough
    assert community.agree("bpm", [90, 92])["value"] == 91.0          # close answers agree and are averaged
    assert community.agree("bpm", [90, 180])["agree"] == 2           # half/double time is the same tempo
    assert community.agree("bpm", [90, 140]) is None                  # disagreement: nothing shared
    assert community.agree("bpm", [90, 91, 91, 140])["value"] == 90.7 # one wild answer is outvoted
    assert community.agree("energy", [0.8, 0.9, 0.1])["value"] == 0.85
    assert community.agree("key", ["A minor", "A minor", "C major"])["value"] == "A minor"
    assert community.agree("key", ["A minor", "C major"]) is None
    assert community.agree("vibes", [["gym", "night"], ["gym"]])["value"] == ["gym"]


def test_values_are_checked():
    assert community.normalise("key", "Am") == "Am"
    assert community.normalise("energy", 75) == 0.75
    assert community.normalise("genre", "hip-hop; pop") == ["Hip-Hop", "Pop"]
    assert community.normalise("vibes", "Late Night!, gym") == ["late night", "gym"]
    for field, bad in [("bpm", 900), ("key", "H major"), ("genre", "space jazz"), ("year", 1500), ("bpm", "fast")]:
        assert _vote("listener-check", field, bad).status_code == 400
    assert client.post("/community/vote", json={"title": TITLE, "field": "bpm", "value": 100}).status_code == 400


def test_a_correction_needs_a_second_listener_before_other_maps_change():
    # One listener's edit changes their own map only
    assert _vote("listener-aaaa", "bpm", 61, ip="10.0.0.1").status_code == 200
    mine = client.post("/map/build", json={"sample": True}, headers={"X-Listener-Id": "listener-aaaa"}).json()
    other = client.post("/map/build", json={"sample": True}, headers={"X-Listener-Id": "listener-zzzz"}).json()
    assert mine["tracks"][0]["bpm"] == 61 and other["tracks"][0]["bpm"] != 61

    # The same person again from another browser on the same network doesn't count twice
    _vote("listener-aaab", "bpm", 61, ip="10.0.0.1")
    other = client.post("/map/build", json={"sample": True}, headers={"X-Listener-Id": "listener-zzzz"}).json()
    assert other["tracks"][0]["bpm"] != 61

    # A second, independent listener agrees: now it is everyone's value
    _vote("listener-bbbb", "bpm", 62, ip="10.0.0.2")
    other = client.post("/map/build", json={"sample": True}).json()
    assert other["tracks"][0]["bpm"] == 61.5
    assert other["meta"]["community_corrected"] >= 1

    view = client.get("/community/song", params={"artist": ARTIST, "title": TITLE},
                      headers={"X-Listener-Id": "listener-aaaa"}).json()
    assert view["stats"]["bpm"]["shared"] == 61.5 and view["stats"]["bpm"]["mine"] == 61
    assert view["stats"]["bpm"]["votes"] == 2

    # Taking a vote back undoes the agreement
    _vote("listener-bbbb", "bpm", None, ip="10.0.0.2")
    view = client.get("/community/song", params={"artist": ARTIST, "title": TITLE}).json()
    assert "shared" not in view["stats"]["bpm"]


def test_vibes_show_on_the_map_and_in_activity():
    t = str(SAMPLE["title"][1])
    _vote("listener-cccc", "vibes", "late night, rainy", ip="10.0.1.1", title=t)
    _vote("listener-dddd", "vibes", ["late night"], ip="10.0.1.2", title=t)
    m = client.post("/map/build", json={"sample": True}).json()
    assert m["tracks"][1]["vibes"] == ["late night"]
    act = client.get("/community/activity").json()
    assert act["votes"] >= 2 and act["recent"][0]["title"] == t


def test_lookups_are_saved_for_everyone():
    community.record_lookup("Some Artist", "Some Song", {"bpm": 128, "key": "8A", "genre": "Electronic",
                                                         "genre_source": "MusicBrainz", "energy": 0.7})
    s = community.song_view("Some Artist", "Some Song")["stats"]
    assert s["bpm"]["looked_up"] == 128 and s["bpm"]["source"] == "Deezer"
    assert s["key"]["looked_up"] == "Am" and s["genre"]["looked_up"] == ["Electronic"]


def test_accounts_are_saved_in_the_database():
    r = client.post("/auth/register", json={"username": "dbuser", "password": "longpassword"})
    assert r.status_code == 200
    assert client.post("/auth/register", json={"username": "dbuser", "password": "longpassword"}).status_code == 400
    tok = client.post("/auth/login", json={"username": "dbuser", "password": "longpassword"}).json()["access_token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()["username"] == "dbuser"
    assert client.post("/auth/login", json={"username": "dbuser", "password": "wrongpassword"}).status_code == 401
    # Signed-in listeners vote as their account
    r = client.post("/community/vote", json={"artist": ARTIST, "title": TITLE, "field": "year", "value": 2001},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json()["stats"]["year"]["mine"] == 2001


def test_taste_match_finds_close_shared_maps():
    m = client.post("/map/build", json={"sample": True}).json()
    share = client.post("/map/share", json={"map": m, "title": "Twin", "listed": True, "sample": True}).json()
    res = client.post("/map/taste-match", json={"sample": True}).json()["matches"]
    twin = next(x for x in res if x["share_id"] == share["id"])
    assert twin["match"] == 100 and twin["shared_songs"] == len(SAMPLE.drop_duplicates(["artist", "title"]))
    # Looking from the share itself leaves it out
    res = client.post("/map/taste-match", json={"share_id": share["id"]}).json()["matches"]
    assert share["id"] not in [x["share_id"] for x in res]
