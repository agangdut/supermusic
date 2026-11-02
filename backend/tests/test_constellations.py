"""Song constellations: saved on the account, checked, and carried into shared maps."""
import uuid

from fastapi.testclient import TestClient

from app.core import constellations
from app.main import app

client = TestClient(app)


def _user():
    name = "c" + uuid.uuid4().hex[:8]
    r = client.post("/auth/register", json={"username": name, "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


STARS = [{"artist": "A", "title": "One"}, {"artist": "B", "title": "Two"}, {"artist": "C", "title": "Three"}]


def test_clean_drops_bad_input():
    out = constellations.clean([
        {"id": "ok1", "name": "  Night drive  ", "color": "#AABBCC", "stars": STARS},
        {"id": "short", "name": "One star", "stars": STARS[:1]},             # a line needs two stars
        {"id": "bad id!", "name": "x" * 99, "color": "red", "stars": STARS},  # fixed, not dropped
        {"id": "ok1", "name": "duplicate id", "stars": STARS},
        "not a dict",
        {"stars": [{"artist": "A"}, {"title": ""}, 5]},                       # no titles
    ])
    assert [c["name"] for c in out] == ["Night drive", "x" * constellations.NAME_MAX]
    assert out[0]["color"] == "#aabbcc"
    assert out[1]["id"] == "c2" and out[1]["color"] == constellations.DEFAULT_COLOR
    assert constellations.clean("nope") == []
    assert len(constellations.clean([{"id": f"i{i}", "stars": STARS} for i in range(99)])) == constellations.MAX_CONSTELLATIONS


def test_saved_on_the_account():
    auth = _user()
    assert client.get("/me/constellations", headers=auth).json() == {"constellations": []}
    r = client.put("/me/constellations", json={"constellations": [{"id": "a", "name": "Gym", "color": "#ff0000", "stars": STARS}]}, headers=auth)
    assert r.status_code == 200
    got = client.get("/me/constellations", headers=auth).json()["constellations"]
    assert [c["name"] for c in got] == ["Gym"] and got[0]["stars"] == STARS
    assert client.get("/me/constellations").status_code == 401


def test_shared_maps_keep_their_constellations():
    m = client.post("/map/build", json={"sample": True}).json()
    t = m["tracks"]
    stars = [{"artist": x.get("artist") or "", "title": x["title"]} for x in t[:3]]
    m["constellations"] = [{"id": "z", "name": "<b>Mine</b>", "color": "#123456", "stars": stars}, {"bad": True}]
    share = client.post("/map/share", json={"map": m, "title": "With stars", "sample": True}).json()
    got = client.get(f"/map/shared/{share['id']}").json()["map"]["constellations"]
    assert len(got) == 1 and got[0]["stars"] == stars and got[0]["name"] == "<b>Mine</b>"  # React escapes it


def _listener(n):
    return {"X-Listener-Id": f"t{uuid.uuid4().hex[:8]}{n}", "X-Forwarded-For": f"10.9.{n}.1"}


def test_atlas_proposal_becomes_official_at_80_percent():
    author = _user()
    keys = ["a|one", "b|two", "c|three"]
    assert client.post("/atlas/constellations", json={"name": "Big Dipper", "song_keys": keys}).status_code == 401
    assert client.post("/atlas/constellations", json={"name": "x", "song_keys": keys[:1]}, headers=author).status_code == 400
    p = client.post("/atlas/constellations", json={"name": "Big Dipper", "color": "#FDE68A", "song_keys": keys}, headers=author).json()
    assert p["status"] == "proposed" and p["song_keys"] == keys and p["color"] == "#fde68a"
    pid = p["id"]
    # The author can't vote on their own
    assert client.post(f"/atlas/constellations/{pid}/vote", json={"up": True}, headers=author).status_code == 400

    voters = [_listener(i) for i in range(6)]
    for v in voters[:4]:
        r = client.post(f"/atlas/constellations/{pid}/vote", json={"up": True}, headers=v).json()
    assert r["yes"] == 4 and r["status"] == "proposed"  # 4 votes: not enough yet
    r = client.post(f"/atlas/constellations/{pid}/vote", json={"up": True}, headers=voters[4]).json()
    assert r["status"] == "official" and r["my_vote"] is True  # 5 of 5
    r = client.post(f"/atlas/constellations/{pid}/vote", json={"up": False}, headers=voters[5]).json()
    assert (r["yes"], r["no"], r["status"]) == (5, 1, "official")  # 83%
    r = client.post(f"/atlas/constellations/{pid}/vote", json={"up": False}, headers=voters[4]).json()
    assert (r["yes"], r["no"], r["status"]) == (4, 2, "proposed")  # changed their mind: 67%
    r = client.post(f"/atlas/constellations/{pid}/vote", json={"up": None}, headers=voters[4]).json()
    assert (r["yes"], r["no"]) == (4, 1)

    listed = client.get("/atlas/constellations", headers=voters[0]).json()
    assert listed["rule"] == {"min_votes": 5, "approve_share": 0.8}
    mine = next(c for c in listed["constellations"] if c["id"] == pid)
    assert mine["my_vote"] is True and mine["name"] == "Big Dipper"

    # Only the author can take it down
    assert client.delete(f"/atlas/constellations/{pid}", headers=_user()).status_code == 403
    assert client.delete(f"/atlas/constellations/{pid}", headers=author).status_code == 200
    assert client.post(f"/atlas/constellations/{pid}/vote", json={"up": True}, headers=voters[0]).status_code == 404


def test_status_rule():
    assert constellations.status_of(4, 0) == "proposed"
    assert constellations.status_of(4, 1) == "official"
    assert constellations.status_of(7, 3) == "proposed"
    assert constellations.status_of(8, 2) == "official"
