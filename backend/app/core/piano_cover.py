"""
Piano cover mode: turn a pop song into a piano arrangement with Pop2Piano.

Pop2Piano (Choi & Lee, ICASSP 2023) is a transformer trained on about 300
hours of pop songs paired with piano covers that people played and posted on
YouTube. Instead of writing down every note it hears, it writes what a pianist
would play: melody on top, accompaniment underneath. Weights (~1 GB) come
from the Hugging Face hub on first use and are cached in data/models/hf.

`composer` picks one of the 21 cover arrangers it learned from (composer1 to
composer21); each has its own style.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

from app.core.config import settings

MODEL_ID = os.getenv("SM_POP2PIANO_MODEL", "sweetcocoa/pop2piano")
COMPOSERS = [f"composer{i}" for i in range(1, 22)]
SAMPLE_RATE = 44100

_model = None
_processor = None
_lock = threading.Lock()


def _load():
    global _model, _processor
    with _lock:
        if _model is None:
            import torch
            from transformers import Pop2PianoForConditionalGeneration, Pop2PianoProcessor

            cache = settings.DATA_DIR / "models" / "hf"
            _processor = Pop2PianoProcessor.from_pretrained(MODEL_ID, cache_dir=cache)
            model = Pop2PianoForConditionalGeneration.from_pretrained(MODEL_ID, cache_dir=cache)
            if not hasattr(model.generation_config, "composer_to_feature_token"):
                # transformers 5 drops unknown keys from generation_config.json; put this one back
                model.generation_config.composer_to_feature_token = _generation_json(cache)["composer_to_feature_token"]
            _model = model.to("cuda" if torch.cuda.is_available() else "cpu").eval()
        return _model, _processor


def _generation_json(cache: Path) -> dict:
    local = Path(MODEL_ID) / "generation_config.json"
    if not local.exists():
        from huggingface_hub import hf_hub_download

        local = Path(hf_hub_download(MODEL_ID, "generation_config.json", cache_dir=cache))
    return json.loads(local.read_text())


def piano_cover(audio_path: str | Path, out_dir: Path | None = None, composer: str = "composer1") -> Path:
    """Arrange a song for solo piano. Returns the MIDI path."""
    import librosa
    import torch

    if composer not in COMPOSERS:
        raise ValueError(f"composer must be one of composer1..composer21, got {composer!r}")
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    out_dir = (out_dir or (settings.PROCESSED_DIR / "midi")) / uuid.uuid4().hex
    out_dir.mkdir(parents=True, exist_ok=True)
    midi_path = out_dir / f"{audio_path.stem}_cover.mid"

    audio, sr = librosa.load(str(audio_path), sr=SAMPLE_RATE, mono=True)
    model, processor = _load()
    with _lock, torch.no_grad():  # one song at a time
        inputs = processor(audio=audio, sampling_rate=sr, return_tensors="pt")
        tokens = model.generate(input_features=inputs["input_features"].to(model.device), composer=composer)
        try:
            pm = processor.batch_decode(token_ids=tokens.cpu(), feature_extractor_output=inputs)["pretty_midi_objects"][0]
        except ValueError as e:  # decoding fails on an empty note list
            raise RuntimeError("Pop2Piano didn't produce any notes for this audio.") from e
    for inst in pm.instruments:
        inst.program, inst.is_drum = 0, False  # acoustic grand piano
    pm.write(str(midi_path))
    return midi_path
