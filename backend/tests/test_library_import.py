from pathlib import Path

import pandas as pd

from app.core.library_import import merge, parse_file, song_key

FIX = Path(__file__).parent / "fixtures" / "exports"


def load(name):
    return parse_file(name, (FIX / name).read_bytes())


def test_song_key_ignores_features_and_case():
    assert song_key("Wale, Rick Ross", "Poor Decisions (feat. Rick Ross & Lupe Fiasco)") == song_key("wale", "Poor Decisions")


def test_exportify_keeps_audio_features():
    df, label = load("exportify.csv")
    assert "Exportify" in label
    row = df[df["title"] == "Here"].iloc[0]
    assert row["artist"] == "Alessia Cara" and row["bpm"] == 120.2 and row["year"] == 2015


def test_spotify_history_counts_plays_and_skips():
    df, label = load("StreamingHistory_music_0.json")
    assert "Spotify" in label
    here = df[df["title"] == "Here"].iloc[0]
    assert here["play_count"] == 2 and here["skip_count"] == 0
    assert df[df["title"] == "the time"].iloc[0]["skip_count"] == 1  # 5 s play


def test_apple_play_history_splits_description():
    df, label = load("Apple Music - Track Play History.csv")
    assert "Apple" in label
    assert set(df["artist"]) == {"Allan Rayman", "Gunna"}


def test_music_app_utf16_export():
    df, label = load("Library.txt")
    assert "Apple Music playlist" in label
    assert df[df["title"] == "Here"].iloc[0]["play_count"] == 12


def test_merge_sums_plays_across_files():
    frames = [load(n)[0] for n in ["exportify.csv", "StreamingHistory_music_0.json", "Library.txt",
                                   "Apple Music - Track Play History.csv"]]
    m = merge(frames)
    here = m[m["title"] == "Here"].iloc[0]
    assert here["play_count"] == 2 + 12          # Spotify history + Music app
    assert here["bpm"] == 120.2                 # from Exportify
    assert here["genre"] in ("canadian pop,pop", "Pop")
    assert len(m) == 5  # Here, the time, Tennessee, Slippin Out Reality, Ghetto Gospel


def test_spotify_extended_history_keeps_dates_and_uri_and_skips_podcasts():
    df, label = load("Streaming_History_Audio_2024.json")
    assert "extended" in label
    here = df[df["title"] == "Here"].iloc[0]
    assert here["play_count"] == 1 and here["skip_count"] == 1
    assert here["first_played"] == "2024-03-01" and here["last_played"] == "2025-06-11"
    assert here["uri"] == "spotify:track:1"
    assert len(df) == 2  # the podcast episode is not a song


def test_spotify_library_json_marks_liked_songs():
    df, label = load("YourLibrary.json")
    assert "liked" in label.lower()
    assert set(df["title"]) == {"Here", "Snooze"} and df["liked"].all()


def test_spotify_playlists_json_lists_each_songs_playlists():
    df, label = load("Playlist1.json")
    assert "playlists" in label.lower()
    here = df[df["title"] == "Here"].iloc[0]
    assert here["playlists"] == "Late night; Gym" and here["added_at"] == "2022-12-01"
    assert len(df) == 2


def test_podcast_history_is_recognised_and_empty():
    df, label = load("StreamingHistory_podcast_0.json")
    assert "podcast" in label.lower() and len(df) == 0


def test_merge_dedupes_a_whole_spotify_account_export():
    names = ["exportify.csv", "StreamingHistory_music_0.json", "Streaming_History_Audio_2024.json",
             "YourLibrary.json", "Playlist1.json", "StreamingHistory_podcast_0.json"]
    m = merge([load(n)[0] for n in names])
    here = m[m["title"] == "Here"].iloc[0]
    assert (m["title"] == "Here").sum() == 1
    assert here["play_count"] == 2 + 1 and here["skip_count"] == 1
    assert here["first_played"] == "2024-03-01" and here["last_played"] == "2026-01-02"
    # an Exportify file is one playlist, named after the file
    assert bool(here["liked"]) and here["playlists"] == "exportify; Late night; Gym"
    assert here["bpm"] == 120.2 and here["uri"] == "spotify:track:1"
    snooze = m[m["title"] == "Snooze"].iloc[0]
    assert bool(snooze["liked"]) and pd.isna(snooze["play_count"]) or snooze["play_count"] == 0


def test_history_records_songs_played_back_to_back():
    rows = [("A", "x", None, 200000, False, "2024-01-01T10:00:00Z"),
            ("B", "y", None, 200000, False, "2024-01-01T10:04:00Z"),
            ("A", "x", None, 200000, False, "2024-01-02T10:00:00Z"),
            ("B", "y", None, 5000, True, "2024-01-02T10:01:00Z"),  # a skip is not a pairing
            ("B", "y", None, 200000, False, "2024-01-02T10:03:00Z"),
            ("C", "z", None, 200000, False, "2024-01-02T12:03:00Z")]  # new session: not paired with B
    from app.core.library_import import _aggregate_plays, parse_partners

    df = _aggregate_plays(rows, "test").set_index("title")
    assert parse_partners(df.loc["A", "played_with"]) == {"y|b": 2}
    assert pd.isna(df.loc["C", "played_with"])
    # merging two histories adds the counts up
    m = merge([df.reset_index(), df.reset_index()]).set_index("title")
    assert parse_partners(m.loc["A", "played_with"]) == {"y|b": 4}
