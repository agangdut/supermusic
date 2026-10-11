import json

import pytest

from app.core import genres, library_import
from app.core.genres import canonical, summarise


@pytest.mark.parametrize("tag,genre", [
    ("Rap/Hip Hop", "Hip-Hop"), ("conscious hip hop", "Hip-Hop"), ("pop rap", "Hip-Hop"), ("uk drill", "Hip-Hop"),
    ("Hip-Hop/Rap", "Hip-Hop"), ("R&B/Soul", "R&B"), ("neo soul", "R&B"), ("rnb", "R&B"),
    ("dance pop", "Pop"), ("synthpop", "Pop"), ("electropop", "Pop"), ("Pop", "Pop"), ("International Pop", "Pop"),
    ("pop rock", "Rock"), ("indie rock", "Rock"), ("pop punk", "Punk"), ("Alternative", "Alternative"),
    ("Dance", "Electronic"), ("deep house", "Electronic"), ("trip hop", "Electronic"), ("Electro", "Electronic"),
    ("Soul & Funk", "Soul"), ("reggaeton", "Latin"), ("k-pop", "K-Pop"), ("Films/Games", "Soundtrack"),
    ("singer-songwriter", "Folk"), ("heavy metal", "Metal"), ("afrobeats", "Afrobeats"),
])
def test_tags_map_to_plain_genres(tag, genre):
    assert canonical(tag) == genre


@pytest.mark.parametrize("tag", ["seen live", "female vocalists", "british", "2010s", "favorites", "Adele"])
def test_non_genre_tags_are_dropped(tag):
    assert canonical(tag) is None


def test_summarise_keeps_strong_genres_only():
    tags = [("soul", 10), ("pop", 8), ("british", 9), ("female vocalists", 7), ("jazz", 1)]
    assert summarise(tags) == ["Soul", "Pop"]
    assert summarise([("rap", 1)]) == ["Hip-Hop"]
    assert summarise([("pop", 10), ("hip hop", 2)]) == ["Pop"]  # one stray tag doesn't relabel


@pytest.fixture
def offline(tmp_path, monkeypatch):
    """Fake Deezer and MusicBrainz so tests never touch the network."""
    monkeypatch.setattr(genres, "_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(library_import, "_cache_dir", lambda: tmp_path)
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    calls = []

    def fake_get(url, timeout=15):
        calls.append(url)
        if "musicbrainz" in url:
            if "Adele" in url:
                return {"artists": [
                    {"name": "Adele", "score": 100, "tags": [{"name": "soul", "count": 12}, {"name": "pop", "count": 9},
                                                             {"name": "british", "count": 11}]},
                    {"name": "Adele", "score": 100, "tags": [{"name": "rap", "count": 1}]},  # a namesake
                ]}
            return {"artists": []}
        if "search" in url:  # Deezer: a rapper's song with the same title comes first
            return {"data": [
                {"id": 1, "title": "Hello", "artist": {"name": "Some Rapper"}, "album": {"id": 10}},
                {"id": 2, "title": "Hello", "artist": {"name": "Adele"}, "album": {"id": 20}},
            ]}
        if "/album/10" in url:
            return {"genres": {"data": [{"name": "Rap/Hip Hop"}]}, "release_date": "2019-01-01"}
        if "/album/20" in url:
            return {"genres": {"data": [{"name": "Pop"}]}, "release_date": "2015-11-20"}
        if "/track/" in url:
            return {"bpm": 79}
        raise AssertionError(url)

    monkeypatch.setattr(genres, "_get", fake_get)
    monkeypatch.setattr(genres, "_mb_get", fake_get)
    monkeypatch.setattr(library_import, "_get", fake_get)
    return calls


def test_lookup_uses_the_right_artist_and_listener_tags(offline):
    info = library_import.lookup("Adele", "Hello", analyse=False)
    assert info["deezer_id"] == 2 and info["year"] == 2015
    assert info["genre"] == "Soul;Pop" and info["genre_source"] == "MusicBrainz"


def test_unknown_artist_gets_no_one_elses_genre(offline):
    info = library_import.lookup("Nobody Famous", "Hello", analyse=False)
    assert "genre" not in info and "deezer_id" not in info


def test_deezer_genre_is_the_fallback(offline, monkeypatch):
    monkeypatch.setattr(genres, "musicbrainz_tags", lambda artist: [])
    info = library_import.lookup("Adele", "Hello", analyse=False)
    assert info["genre"] == "Pop" and info["genre_source"] == "Deezer"


def test_artist_genres_are_cached(offline):
    library_import.lookup("Adele", "Hello", analyse=False)
    library_import.lookup("Adele", "Someone Like You", analyse=False)
    assert sum("musicbrainz" in u for u in offline) == 1


def test_old_cached_deezer_genre_is_ignored(offline, tmp_path):
    key = library_import.song_key("Adele", "Hello")
    import re
    (tmp_path / (re.sub(r"[^a-z0-9|]+", "_", key)[:150] + ".json")).write_text(
        json.dumps({"deezer_id": 2, "genre": "Rap/Hip Hop"}))
    assert library_import.lookup("Adele", "Hello", analyse=False)["genre"] == "Soul;Pop"


def test_lastfm_wins_when_a_key_is_set(offline, monkeypatch):
    monkeypatch.setenv("LASTFM_API_KEY", "x")
    monkeypatch.setattr(genres, "lastfm_tags", lambda artist, title=None: [("indie pop", 100), ("seen live", 90)])
    info = library_import.lookup("Adele", "Hello", analyse=False)
    assert info["genre"] == "Pop" and info["genre_source"] == "Last.fm"
