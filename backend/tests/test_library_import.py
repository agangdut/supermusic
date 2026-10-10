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
