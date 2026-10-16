import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.core import sound
from app.core.music_map import build_map
from app.main import app

client = TestClient(app)
rng = np.random.default_rng(0)


def _unit(v):
    return v / np.linalg.norm(v)


def _library(n_per_group=8):
    """Two groups of songs with the same key/tempo but clearly different sound vectors."""
    base = [_unit(rng.standard_normal(64)) for _ in range(2)]
    rows = []
    for g in range(2):
        for i in range(n_per_group):
            v = _unit(base[g] + 0.15 * rng.standard_normal(64))
            rows.append({"title": f"Song {g}-{i}", "artist": f"Artist {g}{i}", "key": "Am", "bpm": 120,
                         "energy": 0.5, "sound": sound.encode(v)})
    return pd.DataFrame(rows), base


def test_encode_decode_round_trip():
    v = _unit(rng.standard_normal(512))
    out = sound.decode(sound.encode(v))
    assert out.shape == (512,)
    assert float(out @ v) > 0.999
    assert sound.decode("") is None and sound.decode(float("nan")) is None and sound.decode("not base64!") is None


def test_matrix_marks_missing_rows():
    df, _ = _library(2)
    df.loc[1, "sound"] = None
    m = sound.matrix(df)
    assert m.shape == (4, 64)
    assert np.isnan(m[1]).all() and np.isfinite(m[0]).all()
    assert sound.matrix(df.drop(columns=["sound"])) is None


def test_sound_groups_songs_that_tags_cannot_tell_apart():
    df, _ = _library()
    r = build_map(df)
    assert "sound" in r["meta"]["features_used"]
    assert r["meta"]["sound_tracks"] == len(df)
    group = {t["id"]: t["title"].split()[1][0] for t in r["tracks"]}
    sim = [e for e in r["edges"] if e["kind"] == "similar"]
    same = sum(group[e["source"]] == group[e["target"]] for e in sim)
    assert same / len(sim) > 0.9  # links stay within the sound group
    assert any("similar sound" in e["reasons"] for e in sim)


def test_sound_weight_zero_turns_it_off():
    df, _ = _library()
    r = build_map(df.assign(genre="Rock"), opts=None)
    assert "sound" in r["meta"]["features_used"]
    from app.core.music_map import MapOptions

    r = build_map(df.assign(genre="Rock"), MapOptions(weights={"sound": 0}))
    assert "sound" not in r["meta"]["features_used"]


def test_map_without_sound_column_is_unchanged():
    df, _ = _library()
    r = build_map(df.drop(columns=["sound"]))
    assert "sound" not in r["meta"]["features_used"]
    assert r["meta"]["sound_tracks"] == 0


def test_search_ranks_by_text_vector(monkeypatch, user_dir):
    df, base = _library()
    monkeypatch.setattr(sound, "embed_text", lambda texts: np.stack([base[1]]))
    out = sound.search(df, "anything", limit=5)
    assert len(out) == 5
    assert all(df.loc[r["id"], "title"].startswith("Song 1") for r in out)
    assert out[0]["score"] >= out[-1]["score"]

    path = user_dir / "lib.csv"
    df.to_csv(path, index=False)
    r = client.post("/map/search", json={"csv_path": str(path), "query": "dark synths", "limit": 3})
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()["results"]] == [x["id"] for x in out[:3]]


def test_search_needs_sound_data(user_dir):
    df, _ = _library()
    path = user_dir / "lib.csv"
    df.drop(columns=["sound"]).to_csv(path, index=False)
    r = client.post("/map/search", json={"csv_path": str(path), "query": "piano"})
    assert r.status_code == 400


def test_add_sound_uses_local_files_and_caches(monkeypatch, tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"fake audio")
    calls = []

    def fake_embed(data):
        calls.append(data)
        return _unit(np.ones(16))

    monkeypatch.setattr(sound, "embed_audio", fake_embed)
    df = pd.DataFrame([{"title": "A", "artist": "X", "local_path": str(audio)},
                       {"title": "B", "artist": "Y", "local_path": str(tmp_path / "missing.mp3")}])
    monkeypatch.setattr(sound, "_preview", lambda artist, title: None)
    out, have = sound.add_sound(df)
    assert have == 1 and calls == [b"fake audio"]
    assert sound.decode(out.loc[0, "sound"]) is not None and out.loc[1, "sound"] is None
    out2, have2 = sound.add_sound(df)  # second time comes from the cache
    assert have2 == 1 and len(calls) == 1


def test_import_progress_shows_listening_step():
    from app.routes.map import ImportJob

    job = ImportJob([{"file": "a.csv", "type": "CSV", "songs": 3}], enrich=True)
    job.lookup_planned = True
    job.start_listening()
    job.on_listen(1, 3)
    v = job.view()
    assert v["message"].startswith("Listening to previews… 1 of 3")
    step = next(s for s in v["steps"] if s["key"] == "listen")
    assert step["state"] == "active" and step["detail"] == "1 of 3 songs"
    assert v["eta_s"] is not None

    assert step["skippable"]


def test_add_sound_can_be_stopped_early(monkeypatch):
    monkeypatch.setattr(sound, "embed_audio", lambda data: _unit(np.ones(16)))
    monkeypatch.setattr(sound, "_preview", lambda artist, title: b"audio")
    df = pd.DataFrame([{"title": f"Skip {i}", "artist": f"Stopper {i}"} for i in range(5)])
    heard = []
    out, have = sound.add_sound(df, progress=lambda n, t: heard.append(n), stop=lambda: len(heard) >= 2)
    assert have == 2 and heard == [1, 2]


def test_skipping_listening_shows_in_progress():
    from app.routes.map import ImportJob

    job = ImportJob([{"file": "a.csv", "type": "CSV", "songs": 3}], enrich=True)
    job.lookup_planned = True
    job.start_listening()
    job.on_listen(1, 3)
    job.skip_listen = True
    step = next(s for s in job.view()["steps"] if s["key"] == "listen")
    assert step["detail"] == "Skipping…" and not step["skippable"]


def test_songs_you_may_like_follow_sound():
    from app.core.music_map import similar_tracks

    df, _ = _library()
    r = similar_tracks(df, 0, limit=5)
    assert r["basis"] == "sound" and len(r["results"]) == 5
    assert all(df.loc[x["id"], "title"].startswith("Song 0") for x in r["results"])
    assert all(x["id"] != 0 for x in r["results"])
    assert any("similar sound" in x["reasons"] for x in r["results"])


def test_songs_you_may_like_without_sound_and_artist_cap():
    from app.core.music_map import similar_tracks

    df, _ = _library()
    df = df.drop(columns=["sound"]).assign(artist="Same Artist")
    r = similar_tracks(df, 3, limit=5)
    assert r["basis"] == "features"
    assert len(r["results"]) == 2  # at most two picks per artist


def test_like_endpoint_on_sample_library():
    r = client.post("/map/like", json={"sample": True, "id": 0, "limit": 6})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["results"]) == 6 and body["basis"] == "features"
    assert "rarely_played" in body["results"][0]
    assert client.post("/map/like", json={"sample": True, "id": 99999}).status_code == 400


def test_import_listen_limit_caps_previews(monkeypatch):
    import time as _time

    from app.core import library_import

    seen = {}

    def fake_add_sound(df, limit=1500, progress=None, stop=None):
        seen["limit"] = limit
        return df, 0

    monkeypatch.setattr(library_import, "lookup", lambda a, t, analyse=True: {})
    monkeypatch.setattr(sound, "available", lambda: True)
    monkeypatch.setattr(sound, "add_sound", fake_add_sound)
    csv = "title,artist\n" + "\n".join(f"Cap {i},Capper {i}" for i in range(5))
    r = client.post("/map/import", files={"files": ("l.csv", csv, "text/csv")},
                    data={"enrich": "true", "listen_limit": "3"})
    job_id = r.json()["id"]
    for _ in range(200):
        if client.get(f"/map/import/{job_id}").json()["status"] != "running":
            break
        _time.sleep(0.05)
    assert seen["limit"] == 3


def test_tracks_carry_spotify_and_youtube_links():
    df, _ = _library(3)
    df["uri"] = ["spotify:track:abc123", None, "nope"] * 2
    df["youtube_url"] = [None, "https://youtu.be/xyz", None] * 2
    t = build_map(df)["tracks"]
    assert t[0]["spotify_url"] == "https://open.spotify.com/track/abc123" and "youtube_url" not in t[0]
    assert t[1]["youtube_url"] == "https://youtu.be/xyz" and "spotify_url" not in t[1]
    assert "spotify_url" not in t[2]
