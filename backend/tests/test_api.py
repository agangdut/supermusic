import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.parametrize(
    "path",
    ["/midi/convert", "/stems/separate", "/csv/enrich", "/tracks/download"],
)
def test_job_routes_are_mounted_once(path):
    paths = app.openapi()["paths"]
    assert path in paths
    area = path.split("/")[1]
    assert f"/{area}{path}" not in paths


def test_unknown_job_is_404():
    assert client.get("/midi/jobs/does-not-exist").status_code == 404


def test_upload_csv_returns_server_path():
    r = client.post(
        "/upload/csv",
        files={"file": ("tracks.csv", b"title,artist\nSong,Band\n", "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["path"].endswith("tracks.csv")


def test_upload_rejects_wrong_extension():
    r = client.post(
        "/upload/audio",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400


def test_register_login_me():
    creds = {"username": "tester", "email": "t@example.com", "password": "correct-horse"}
    r = client.post("/auth/register", json=creds)
    assert r.status_code == 200, r.text
    r = client.post("/auth/login", json={"username": "tester", "password": "correct-horse"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "tester"
