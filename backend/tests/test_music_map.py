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
