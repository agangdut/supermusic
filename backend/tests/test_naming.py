from app.utils.storage import output_name, save_bytes, song_title


def test_song_title_drops_video_words_and_counters():
    assert song_title("G Herbo - 1 Chance (Official Music Video).mp3") == "G Herbo - 1 Chance"
    assert song_title("Gunna - the time (Official Lyric Video) (2).mp3") == "Gunna - the time"
    assert song_title("Meek Mill - Who Decides War [Official Visualizer]_1.wav") == "Meek Mill - Who Decides War"
    assert song_title("Waxahatchee - Right Back to It (feat. MJ Lenderman).mp3") == (
        "Waxahatchee - Right Back to It (feat. MJ Lenderman)"
    )
    assert song_title("my_song.mp3") == "my song"


def test_output_name_adds_what_the_file_is():
    assert output_name("/data/raw/uploads/audio/Free Game.mp3", "Full band, two hands", ".mid") == (
        "Free Game (Full band, two hands).mid"
    )
    assert output_name("Free Game.mp3", "", ".mp3") == "Free Game.mp3"


def test_save_bytes_keeps_both_files_when_a_name_repeats():
    first = save_bytes("Same Song (Piano).mid", b"1")
    second = save_bytes("Same Song (Piano).mid", b"2")
    assert first.endswith("Same Song (Piano).mid")
    assert second.endswith("Same Song (Piano) (2).mid")
    assert save_bytes('Bad: name?.mid', b"x").endswith("Bad name.mid")
