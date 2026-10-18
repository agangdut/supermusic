"""Password reset by email, reports and the admin page, and visitor stats."""
import json
import re
import secrets
import uuid

from fastapi.testclient import TestClient

from app.core import mailer, map_share, store
from app.main import app

client = TestClient(app)
BROWSER = {"User-Agent": "Mozilla/5.0 (Macintosh) Firefox/130.0", "X-Listener-Id": "listener-test-1234"}


def _user(name=None, email=None):
    name = name or f"u{uuid.uuid4().hex[:8]}"
    r = client.post("/auth/register", json={"username": name, "password": "password123", "email": email})
    assert r.status_code == 200, r.text
    return name, {"Authorization": f"Bearer {r.json()['access_token']}"}


def _share(owner=None, title="A map"):
    share_id = secrets.token_urlsafe(6)
    folder = map_share.share_dir() / share_id
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({"id": share_id, "title": title, "owner": owner, "listed": True}))
    return share_id


def _sent(monkeypatch):
    outbox = []
    monkeypatch.setattr(mailer, "enabled", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda to, subject, text: outbox.append((to, subject, text)) or True)
    return outbox


# ---- password reset -----------------------------------------------------------------------

def test_reset_link_by_username_or_email_sets_a_new_password(monkeypatch):
    outbox = _sent(monkeypatch)
    name, _ = _user(email=f"{uuid.uuid4().hex[:6]}@example.com")
    email = client.get("/auth/me", headers=_user_auth(name)).json()["email"]

    assert client.post("/auth/forgot", json={"login": email.upper()}).json() == {"sent": True}
    assert len(outbox) == 1 and outbox[0][0] == email
    token = re.search(r"/reset\?token=(\S+)", outbox[0][2]).group(1)

    r = client.post("/auth/reset", json={"token": token, "password": "brand-new-pass"})
    assert r.status_code == 200 and r.json()["access_token"]
    assert client.post("/auth/login", json={"username": name, "password": "password123"}).status_code == 401
    assert client.post("/auth/login", json={"username": name, "password": "brand-new-pass"}).status_code == 200
    # one use only
    assert client.post("/auth/reset", json={"token": token, "password": "another-pass"}).status_code == 400

    # by username works too, and only the newest link counts
    client.post("/auth/forgot", json={"login": name})
    client.post("/auth/forgot", json={"login": name})
    first, second = [re.search(r"token=(\S+)", m[2]).group(1) for m in outbox[1:3]]
    assert client.post("/auth/reset", json={"token": first, "password": "another-pass"}).status_code == 400
    assert client.post("/auth/reset", json={"token": second, "password": "another-pass"}).status_code == 200


def _user_auth(name, password="password123"):
    return {"Authorization": f"Bearer {client.post('/auth/login', json={'username': name, 'password': password}).json()['access_token']}"}


def test_forgot_says_the_same_for_unknown_accounts_and_accounts_without_email(monkeypatch):
    outbox = _sent(monkeypatch)
    name, _ = _user()  # no email
    assert client.post("/auth/forgot", json={"login": name}).json() == {"sent": True}
    assert client.post("/auth/forgot", json={"login": "nobody-at-all"}).json() == {"sent": True}
    assert outbox == []


def test_expired_links_dont_work(monkeypatch):
    outbox = _sent(monkeypatch)
    name, _ = _user(email="old@example.com")
    client.post("/auth/forgot", json={"login": name})
    token = re.search(r"token=(\S+)", outbox[-1][2]).group(1)
    store.connect().execute("UPDATE password_resets SET expires_at = 0 WHERE username = ?", (name,))
    assert client.post("/auth/reset", json={"token": token, "password": "brand-new-pass"}).status_code == 400


def test_changing_email_needs_the_password():
    name, auth = _user()
    assert client.post("/auth/me/email", json={"email": "me@example.com", "password": "wrong"}, headers=auth).status_code == 401
    assert client.post("/auth/me/email", json={"email": "not an email", "password": "password123"}, headers=auth).status_code == 400
    assert client.post("/auth/me/email", json={"email": "me@example.com", "password": "password123"}, headers=auth).status_code == 200
    assert client.get("/auth/me", headers=auth).json()["email"] == "me@example.com"


def test_production_without_mail_says_reset_is_unavailable(monkeypatch):
    monkeypatch.setenv("SM_ENV", "production")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert client.get("/auth/reset-available").json() == {"enabled": False}
    assert client.post("/auth/forgot", json={"login": "someone"}).status_code == 503


# ---- reports and the admin page -----------------------------------------------------------

def test_reports_reach_the_admin_who_can_remove_the_map(monkeypatch):
    admin_name, admin_auth = _user()
    monkeypatch.setenv("SM_ADMINS", f"someone-else, {admin_name.upper()}")
    owner, _ = _user()
    share_id = _share(owner)

    r = client.post("/reports", json={"kind": "map", "target": share_id, "reason": "spam", "details": "ads"}, headers=BROWSER)
    assert r.status_code == 200 and not r.json()["already"]
    assert client.post("/reports", json={"kind": "map", "target": share_id, "reason": "spam"}, headers=BROWSER).json()["already"]
    assert client.post("/reports", json={"kind": "map", "target": "nope1234", "reason": "spam"}, headers=BROWSER).status_code == 404
    assert client.post("/reports", json={"kind": "map", "target": share_id, "reason": "bad"}, headers=BROWSER).status_code == 400

    # strangers and signed-in non-admins can't see the admin page
    _, plain_auth = _user()
    assert client.get("/admin/reports").status_code == 401
    assert client.get("/admin/reports", headers=plain_auth).status_code == 403
    assert client.get("/auth/me", headers=plain_auth).json()["is_admin"] is False
    assert client.get("/auth/me", headers=admin_auth).json()["is_admin"] is True

    reports = client.get("/admin/reports", headers=admin_auth).json()["reports"]
    mine = [g for g in reports if g["target"] == share_id][0]
    assert mine["item"]["title"] == "A map" and mine["reasons"] == {"spam": 1} and mine["notes"] == ["ads"]

    done = client.post(f"/admin/reports/{mine['id']}", json={"action": "remove"}, headers=admin_auth).json()
    assert done["removed"] and map_share.read_meta(share_id) is None
    assert share_id not in [g["target"] for g in client.get("/admin/reports", headers=admin_auth).json()["reports"]]
    assert share_id in [g["target"] for g in client.get("/admin/reports?status=removed", headers=admin_auth).json()["reports"]]


def test_dismissing_keeps_it_and_profile_removal_clears_name_and_bio(monkeypatch):
    admin_name, admin_auth = _user()
    monkeypatch.setenv("SM_ADMINS", admin_name)
    bad, bad_auth = _user()
    client.patch("/auth/me", json={"display_name": "Rude", "bio": "rude words"}, headers=bad_auth)

    rid = client.post("/reports", json={"kind": "profile", "target": bad, "reason": "offensive"}, headers=BROWSER).json()["id"]
    client.post(f"/admin/reports/{rid}", json={"action": "dismiss"}, headers=admin_auth)
    assert client.get("/auth/me", headers=bad_auth).json()["bio"] == "rude words"

    rid = client.post("/reports", json={"kind": "profile", "target": bad, "reason": "offensive"}, headers=BROWSER).json()["id"]
    client.post(f"/admin/reports/{rid}", json={"action": "remove"}, headers=admin_auth)
    me = client.get("/auth/me", headers=bad_auth).json()
    assert me["bio"] == "" and me["display_name"] == bad

    # pins can be reported and removed too
    pin = client.post("/atlas/pins", json={"song_key": "a|b", "text": "spammy link"}, headers=BROWSER).json()
    rid = client.post("/reports", json={"kind": "pin", "target": str(pin["id"]), "reason": "spam"}, headers=BROWSER).json()["id"]
    assert client.post(f"/admin/reports/{rid}", json={"action": "remove"}, headers=admin_auth).json()["removed"]

    # and an account can be deleted, but not an admin's
    assert client.post(f"/admin/users/{bad}/delete", headers=admin_auth).json()["deleted"]
    assert client.post(f"/admin/users/{admin_name}/delete", headers=admin_auth).status_code == 400


# ---- visitor stats ------------------------------------------------------------------------

def test_page_views_count_visitors_without_keeping_addresses(monkeypatch):
    admin_name, admin_auth = _user()
    monkeypatch.setenv("SM_ADMINS", admin_name)
    before = client.get("/admin/stats?days=7", headers=admin_auth).json()["totals"]

    for path in ["/", "/atlas", "/u/[username]"]:
        assert client.post("/stats/view", json={"path": path, "referrer": "https://www.reddit.com/r/music"}, headers=BROWSER).json()["ok"]
    assert not client.post("/stats/view", json={"path": "/"}, headers={"User-Agent": "Googlebot/2.1"}).json()["ok"]
    assert not client.post("/stats/view", json={"path": "/", "referrer": None}, headers={**BROWSER, "DNT": "1"}).json()["ok"]
    assert not client.post("/stats/view", json={"path": "javascript:alert(1)"}, headers=BROWSER).json()["ok"]

    s = client.get("/admin/stats?days=7", headers=admin_auth).json()
    assert len(s["series"]) == 7
    assert s["totals"]["views"] == before["views"] + 3
    assert s["totals"]["visitors"] <= before["visitors"] + 1  # one browser, one visitor
    assert any(r["referrer"] == "reddit.com" for r in s["referrers"])
    rows = store.connect().execute("SELECT * FROM page_views").fetchall()
    assert all("testclient" not in r["visitor"] and len(r["visitor"]) == 16 for r in rows)
    assert client.get("/admin/stats").status_code == 401
