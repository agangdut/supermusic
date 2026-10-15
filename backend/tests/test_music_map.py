import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.music_map import build_map, harmonic_match, parse_key
from app.main import app

client = TestClient(app)


@pytest.mark.parametrize(
    "raw, mode, expected",
    [
        ("Am", None, "8A"),
        ("A minor", None, "8A"),
        ("C", None, "8B"),
        ("C#m", None, "12A"),
        ("Bb", None, "6B"),
        ("8A", None, "8A"),
        (9, 0, "8A"),      # Spotify: pitch class 9 (A), mode 0 (minor)
        (0, 1, "8B"),      # C major
    ],
)
def test_parse_key(raw, mode, expected):
    assert parse_key(raw, mode).camelot == expected


def test_parse_key_rejects_junk():
    assert parse_key("hello") is None
    assert parse_key(None) is None


def test_harmonic_match():
    assert "relative" in harmonic_match(parse_key("Am"), parse_key("C"))
    assert "neighbouring" in harmonic_match(parse_key("Am"), parse_key("Em"))
    assert harmonic_match(parse_key("Am"), parse_key("F#")) is None


def test_sample_map_has_clusters_links_and_picks():
    r = client.post("/map/build", json={"sample": True})
    assert r.status_code == 200, r.text
    m = r.json()
    assert len(m["tracks"]) > 100
    assert len(m["clusters"]) >= 3
    assert m["hidden_connections"], "sample should surface cross-cluster matches"
    assert m["recommendations"], "sample has play counts, so there should be picks"
    plays = {t["id"]: t["plays"] for t in m["tracks"]}
    loved = sorted(plays.values())[len(plays) // 2]
    assert all(plays[r["id"]] <= loved for r in m["recommendations"])
    assert all(r["id"] != r["because_you_play"] for r in m["recommendations"])


def test_map_without_listening_data():
    df = pd.DataFrame({
        "title": [f"t{i}" for i in range(20)],
        "genre": ["rock"] * 10 + ["jazz"] * 10,
        "key": ["E", "A"] * 10,
        "bpm": [120 + i for i in range(10)] + [90 + i for i in range(10)],
    })
    m = build_map(df)
    assert m["meta"]["has_listening_data"] is False
    assert m["recommendations"] == []
    assert {t["cluster"] for t in m["tracks"]}


def test_map_needs_comparable_columns():
    with pytest.raises(ValueError):
        build_map(pd.DataFrame({"title": ["a", "b", "c"], "artist": ["x", "y", "z"]}))


def test_spotify_genre_tags_become_broad_labels():
    """Exportify gives each song many detailed tags; labels should name the broad genre,
    not whichever tag ("rap") happens to be most common."""
    import random

    from app.core.music_map import MapOptions, build_map

    artists = {
        "Drake": "canadian hip hop,canadian pop,hip hop,pop rap,rap,toronto rap",
        "Travis Scott": "hip hop,rap,slap house",
        "Taylor Swift": "pop",
        "Dua Lipa": "dance pop,pop,uk pop",
        "Arctic Monkeys": "garage rock,modern rock,permanent wave,rock,sheffield indie",
        "Bad Bunny": "reggaeton,trap latino,urbano latino",
    }
    rnd = random.Random(0)
    rows = [{"title": f"{a} {k}", "artist": a, "genre": g, "bpm": rnd.uniform(80, 150), "energy": rnd.random()}
            for a, g in artists.items() for k in range(10)]
    m = build_map(pd.DataFrame(rows), MapOptions(weights={"genre": 2.0}))
    by_artist = {t["artist"]: t["genre"] for t in m["tracks"]}
    assert by_artist == {"Drake": "Hip-Hop", "Travis Scott": "Hip-Hop", "Taylor Swift": "Pop", "Dua Lipa": "Pop",
                         "Arctic Monkeys": "Rock", "Bad Bunny": "Latin"}
    labels = {g["name"] for c in m["clusters"] for g in c.get("top_genres", [])}
    assert labels <= {"Hip-Hop", "Pop", "Rock", "Latin"}
    drake = next(t for t in m["tracks"] if t["artist"] == "Drake")
    assert "toronto rap" in drake["styles"]  # the detail is still there


def test_stats_and_track_extras_from_listening_history():
    import numpy as np

    rng = np.random.default_rng(3)
    n = 120
    df = pd.DataFrame({
        "title": [f"Song {i}" for i in range(n)],
        "artist": [f"Artist {i % 9}" for i in range(n)],
        "genre": rng.choice(["pop", "hip hop", "rock", "jazz"], n),
        "key": rng.integers(0, 12, n), "mode": rng.integers(0, 2, n),
        "bpm": rng.normal(110, 20, n).round(1),
        "energy": rng.random(n), "year": rng.integers(1980, 2024, n),
        "play_count": rng.integers(0, 50, n), "skip_count": rng.integers(0, 8, n),
        "first_played": [f"20{15 + i % 8}-0{1 + i % 9}-01" for i in range(n)],
        "last_played": [f"20{17 + i % 8}-0{1 + i % 9}-01" for i in range(n)],
    })
    df.loc[0, ["play_count", "last_played"]] = [500, "2018-01-01"]  # a favourite left behind
    r = build_map(df)
    s = r["stats"]
    assert s["overview"]["songs"] == n and s["overview"]["artists"] == 9
    assert s["overview"]["plays"] == int(df["play_count"].sum())
    assert abs(sum(g["library_share"] for g in s["genres"]) - 1) < 0.02
    assert {"decades", "keys", "tempo", "concentration", "diversity", "top_artists"} <= set(s)
    assert s["timeline"]["by"] == "year" and sum(p["new_songs"] for p in s["timeline"]["periods"]) == n
    assert 0 in [x["id"] for x in s["lists"]["rediscover"]]
    t = r["tracks"][0]
    assert t["year"] and t["first_played"] and t["energy"] is not None and t["skips"] is not None


def test_hidden_links_found_when_only_some_songs_have_key_and_tempo():
    import numpy as np

    rng = np.random.default_rng(7)
    n = 400
    df = pd.DataFrame({
        "title": [f"Song {i}" for i in range(n)],
        "artist": [f"Artist {i % 40}" for i in range(n)],
        "genre": rng.choice(["pop", "hip hop", "rock", "jazz", "house"], n),
        "year": rng.integers(1980, 2024, n),
    })
    has = rng.random(n) < 0.3  # like a big library where only the most-played were looked up
    df["key"] = [rng.choice(["Am", "C", "Em", "G"]) if h else None for h in has]
    df["bpm"] = np.where(has, rng.choice([90, 120, 128], n), np.nan)
    r = build_map(df)
    assert r["meta"]["musical_tracks"] == has.sum()
    assert len(r["hidden_connections"]) > 0
    assert all(has[h["source"]] and has[h["target"]] for h in r["hidden_connections"])


def test_clusters_describe_their_contents():
    from app.routes.map import SAMPLE_CSV

    r = build_map(pd.read_csv(SAMPLE_CSV))
    c = r["clusters"][0]
    assert c["top_tracks"] and c["top_artists"]
    names = [c["label"].split(" · ")[0] for c in r["clusters"]]
    assert len(names) == len(set(names))
