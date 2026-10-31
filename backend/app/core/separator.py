from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

from app.core.config import settings


def _which(bin_name: str) -> Optional[str]:
    return shutil.which(bin_name)


def separate_stems(audio_path: str | Path, out_dir: Path | None = None, model: str = "htdemucs",
                   two_stems: Optional[str] = None) -> Dict[str, str]:
    """
    Separate stems using demucs CLI if available.
    Returns a mapping {stem_name: path}. If demucs is not installed, raises a clear error.

    Install demucs:
      pip install demucs
    Usage notes:
      - demucs writes into a subfolder under the current working directory by default.
    """
    demucs = _which(settings.DEMUCS_BIN)
    if not demucs:
        raise RuntimeError(
            "Demucs not found on PATH. Install with `pip install demucs` "
            "or skip separation."
        )

    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    out_dir = out_dir or (settings.INTERIM_DIR / "stems")
    out_dir.mkdir(parents=True, exist_ok=True)

    # demucs -n htdemucs -o OUT input.wav
    cmd = [demucs, "-n", model, "-o", str(out_dir), str(audio_path)]
    if two_stems:  # e.g. "vocals" → vocals.wav + no_vocals.wav, about twice as fast
        cmd[1:1] = ["--two-stems", two_stems]
    # Lower priority than the website: Demucs takes every CPU core for minutes, and
    # without this the Atlas, Map and everything else crawl while stems are made
    nicer = (lambda: os.nice(10)) if hasattr(os, "nice") else None
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, preexec_fn=nicer)
    if proc.returncode in (-9, 137):
        raise RuntimeError("demucs was killed: the server ran out of memory on this song")
    if proc.returncode != 0:
        raise RuntimeError(f"demucs failed ({proc.returncode}):\n{proc.stdout}")

    # demucs creates e.g. OUT/<model>/<file stem>/{drums,bass,other,vocals}.wav
    produced_parent = out_dir / model / audio_path.stem
    if not produced_parent.exists():
        # Different demucs versions vary the depth
        produced_parent = next(out_dir.glob(f"{model}/*"), None)

    if produced_parent is None or not produced_parent.exists():
        # try alternate depth
        alt = next(out_dir.glob("*"), None)
        if not alt:
            raise RuntimeError("Demucs completed but could not locate output folder.")
        produced_parent = alt

    stems = {}
    for stem_file in produced_parent.rglob("*.wav"):
        stems[stem_file.stem] = str(stem_file)
    if not stems:
        raise RuntimeError("No stems found after demucs separation.")

    return stems
