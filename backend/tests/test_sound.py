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


def test_search_ranks_by_text_vector(monkeypatch, tmp_path):
    df, base = _library()
    monkeypatch.setattr(sound, "embed_text", lambda texts: np.stack([base[1]]))
    out = sound.search(df, "anything", limit=5)
    assert len(out) == 5
    assert all(df.loc[r["id"], "title"].startswith("Song 1") for r in out)
    assert out[0]["score"] >= out[-1]["score"]

    path = tmp_path / "lib.csv"
    df.to_csv(path, index=False)
    r = client.post("/map/search", json={"csv_path": str(path), "query": "dark synths", "limit": 3})
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()["results"]] == [x["id"] for x in out[:3]]


def test_search_needs_sound_data(tmp_path):
    df, _ = _library()
    path = tmp_path / "lib.csv"
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
