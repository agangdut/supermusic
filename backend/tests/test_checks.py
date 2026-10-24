import uuid

from fastapi.testclient import TestClient

from app.core import checks
from app.main import app

client = TestClient(app)


def _user():
    name = f"u{uuid.uuid4().hex[:8]}"
    r = client.post("/auth/register", json={"username": name, "password": "password123", "display_name": name})
    assert r.status_code == 200, r.text
    return name, {"Authorization": f"Bearer {r.json()['access_token']}"}


def _song():
    return {"artist": f"Check Artist {uuid.uuid4().hex[:6]}", "title": "Check Song"}


def _vote(song, field, value, headers, ip):
    r = client.post("/community/vote", json={**song, "field": field, "value": value},
                    headers={**headers, "X-Forwarded-For": ip})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_check_is_a_yes_no_question_with_alternatives():
    song = _song()
    q = client.post("/community/check", json={**song, "bpm": 120, "key": "Am"},
                    headers={"X-Listener-Id": "checker-aaaa"}).json()["question"]
    assert q["field"] == "bpm" and "120 BPM" in q["prompt"]
    assert [a["value"] for a in q["alternatives"]] == [60, 240]
    # Once you've answered the tempo, the next check is the key, with chords to compare
    _vote(song, "bpm", 120, {"X-Listener-Id": "checker-aaaa"}, "10.1.0.1")
    q = client.post("/community/check", json={**song, "bpm": 120, "key": "Am"},
                    headers={"X-Listener-Id": "checker-aaaa"}).json()["question"]
    assert q["field"] == "key" and q["shown"] == "A minor" and q["chord"] == [57, 60, 64]
    assert q["alternatives"][0]["label"] == "C major"
    # Nothing known about a song: nothing to ask
    assert client.post("/community/check", json=_song()).json()["question"] is None


def test_settled_stats_stop_being_asked_and_votes_report_their_effect():
    song = _song()
    res = None
    for i in range(checks.SETTLED):
        res = _vote(song, "year", 2001, {"X-Listener-Id": f"settler-{i:04d}"}, f"10.2.0.{i}")
        if i == 0:
            assert res["check"]["agreed"] is False and res["check"]["agree"] == 0
    assert res["check"]["settled"] and res["check"]["agree"] == checks.SETTLED
    left = client.post("/community/needs-check", json={"songs": [{**song, "year": 2001}]},
                       headers={"X-Listener-Id": "newcomer-0000"}).json()["songs"]
    assert left == []
    other = _song()
    left = client.post("/community/needs-check", json={"songs": [{**song, "year": 2001}, {**other, "bpm": 99}]},
                       headers={"X-Listener-Id": "newcomer-0000"}).json()["songs"]
    assert left == [{**other, "fields": ["bpm"]}]


def test_only_agreed_fixes_earn_badges_and_rewards():
    a, a_auth = _user()
    b, b_auth = _user()
    for n in range(checks.BADGE_AT):
        song = _song()
        _vote(song, "genre", "Jazz", a_auth, "10.3.0.1")
        _vote(song, "genre", "Jazz", b_auth, "10.3.0.2")
        _vote(song, "bpm", 100, a_auth, "10.3.0.1")
        _vote(song, "bpm", 101, b_auth, "10.3.0.2")
    lonely = _song()
    _vote(lonely, "bpm", 140, a_auth, "10.3.0.1")  # nobody agrees: no reward
    impact = client.get("/community/impact", headers=a_auth).json()
    assert impact["agreed"] == 2 * checks.BADGE_AT and impact["settled_this_month"] == checks.BADGE_AT
    labels = {x["label"] for x in impact["badges"]}
    assert {"Tempo checker: Jazz", "Genre guide: Jazz"} <= labels
    assert impact["rewards"]["next"]["left"] == 25 - 2 * checks.BADGE_AT
    rep = client.get(f"/users/{a}").json()["reputation"]
    assert any(x["label"] == "Tempo checker: Jazz" for x in rep["badges"])
    assert rep["points"] == 10 * rep["agreed"] + 5 * rep["first"]
    board = client.get("/leaderboards").json()["checkers"]
    assert any(p["username"] in (a, b) for p in board.get("Jazz", []))


def test_rewards_milestones():
    assert checks.rewards(0)["next"]["left"] == 25 and checks.rewards(0)["earned"] == []
    r = checks.rewards(60)
    assert [e["id"] for e in r["earned"]] == ["plus_week", "studio_10"] and r["next"]["id"] == "plus_month"
