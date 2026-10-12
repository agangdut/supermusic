"""
Filesystem utilities for SuperMusic.
"""

from __future__ import annotations
import json
import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Iterable, List, Union

PathLike = Union[str, Path]

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac"}


def ensure_dir(path: PathLike) -> Path:
    """
    Ensure a directory exists; return it as Path.
    """
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_audio_files(root: PathLike, recursive: bool = True) -> List[Path]:
    """
    List audio files under a root folder.
    """
    root = Path(root)
    if recursive:
        return [p for p in root.rglob("*") if p.suffix.lower() in AUDIO_EXTS]
    return [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTS]


def read_json(path: PathLike):
    """
    Read JSON from file.
    """
    with open(Path(path), "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(obj, path: PathLike, indent: int = 2):
    """
    Write JSON to file (atomic).
    """
    data = json.dumps(obj, indent=indent, ensure_ascii=False)
    atomic_write_text(Path(path), data)


def sha256sum(path: PathLike, chunk_size: int = 1 << 20) -> str:
    """
    Compute SHA-256 checksum of a file.
    """
    h = hashlib.sha256()
    with open(Path(path), "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_bytes(path: PathLike, data: bytes) -> None:
    """
    Atomically write bytes to a file (safe on Windows & POSIX).
    """
    path = Path(path)
    tmp_dir = path.parent
    ensure_dir(tmp_dir)
    with tempfile.NamedTemporaryFile(dir=tmp_dir, delete=False) as tmp:
        tmp.write(data)
        tmp.flush()
        tmp_name = tmp.name
    shutil.move(tmp_name, path)


def atomic_write_text(path: PathLike, data: str) -> None:
    """
    Atomically write text (UTF-8) to a file.
    """
    atomic_write_bytes(path, data.encode("utf-8"))


def safe_stem(p: PathLike) -> str:
    """
    Return a filesystem-friendly stem (no spaces, lowercase, basic ascii-ish).
    """
    s = Path(p).stem
    s = s.strip().lower().replace(" ", "_")
    # keep alphanum, dash, underscore, dot
    return "".join(ch for ch in s if ch.isalnum() or ch in "-_.")
