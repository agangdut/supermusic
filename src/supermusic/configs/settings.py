# src/supermusic/configs/settings.py
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    data_dir: Path = Path("./data")
    raw_dir: Path = None
    processed_dir: Path = None
    separation_engine: str = "demucs"
    vocals_model: str = "basic-pitch"
    instr_model: str = "onsets-and-frames"

    model_config = SettingsConfigDict(env_prefix="SUPER_MUSIC_")

    def __post_init__(self):  # if using pydantic v2, use model_post_init
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
