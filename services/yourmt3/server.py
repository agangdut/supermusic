"""
Small HTTP wrapper around YourMT3+ so the main backend can call it.

POST /transcribe {"audio_path": "/app/data/...", "out_dir": "/app/data/..."}
  -> {"midi_path": "...", "seconds": 12.3, "device": "cuda"}

Paths are inside the shared ./data volume.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "amt" / "src"))
os.chdir(ROOT)  # the model looks for checkpoints under ./amt/logs

import torch  # noqa: E402
import torchaudio  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel  # noqa: E402

EXP = "mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b36_nops"
CKPT_URL = f"https://huggingface.co/mimbres/YourMT3/resolve/main/logs/2024/{EXP}/checkpoints/last.ckpt"
CKPT = ROOT / "amt" / "logs" / "2024" / EXP / "checkpoints" / "last.ckpt"
CKPT_BYTES = 561_544_628

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
# Turing GPUs (RTX 20xx) have no bf16, so use fp16 on GPU and fp32 on CPU
PRECISION = "16" if DEVICE == "cuda" else "32"
ARGS = [f"{EXP}@last.ckpt", "-p", "2024", "-tk", "mc13_full_plus_256", "-dec", "multi-t5",
        "-nl", "26", "-enc", "perceiver-tf", "-sqr", "1", "-ff", "moe", "-wf", "4", "-nmoe", "8",
        "-kmoe", "2", "-act", "silu", "-epe", "rope", "-rp", "1", "-ac", "spec", "-hop", "300",
        "-atc", "1", "-pr", PRECISION]

app = FastAPI(title="YourMT3+")
_model = None
_lock = threading.Lock()


def ensure_checkpoint() -> None:
    if CKPT.exists() and CKPT.stat().st_size == CKPT_BYTES:
        return
    # amt/logs is a symlink into the data volume; make sure its target exists
    Path(os.path.realpath(ROOT / "amt" / "logs")).mkdir(parents=True, exist_ok=True)
    CKPT.parent.mkdir(parents=True, exist_ok=True)
    tmp = CKPT.with_suffix(".part")
    urllib.request.urlretrieve(CKPT_URL, tmp)
    if tmp.stat().st_size != CKPT_BYTES:
        raise RuntimeError("YourMT3+ checkpoint download was incomplete")
    tmp.replace(CKPT)


def model():
    global _model
    with _lock:
        if _model is None:
            ensure_checkpoint()
            from model_helper import load_model_checkpoint

            _model = load_model_checkpoint(args=ARGS, device="cpu").to(DEVICE)
        return _model


def transcribe(audio_path: Path, out_dir: Path) -> Path:
    from utils.audio import slice_padded_array
    from utils.event2note import merge_zipped_note_events_and_ties_to_notes
    from utils.note2event import mix_notes
    from utils.utils import write_model_output_as_midi

    m = model()
    audio, sr = torchaudio.load(str(audio_path))
    audio = torch.mean(audio, dim=0).unsqueeze(0)
    audio = torchaudio.functional.resample(audio, sr, m.audio_cfg["sample_rate"])
    frames = m.audio_cfg["input_frames"]
    segs = slice_padded_array(audio, frames, frames)
    segs = torch.from_numpy(segs.astype("float32")).to(DEVICE).unsqueeze(1)
    # Weights stay fp32 (the spectrogram needs it); autocast runs the transformer in fp16 on the GPU
    with _lock, torch.inference_mode(), torch.autocast(DEVICE, dtype=torch.float16, enabled=PRECISION == "16"):
        tokens, _ = m.inference_file(bsz=8, audio_segments=segs)
    starts = [frames * i / m.audio_cfg["sample_rate"] for i in range(segs.shape[0])]
    notes_per_channel = []
    errors = Counter()
    for ch in range(m.task_manager.num_decoding_channels):
        zipped, _, _ = m.task_manager.detokenize_list_batches([t[:, ch, :] for t in tokens], starts, return_events=True)
        notes, err = merge_zipped_note_events_and_ties_to_notes(zipped)
        notes_per_channel.append(notes)
        errors += err
    out_dir.mkdir(parents=True, exist_ok=True)
    write_model_output_as_midi(mix_notes(notes_per_channel), str(out_dir), audio_path.stem, m.midi_output_inverse_vocab)
    return out_dir / "model_output" / f"{audio_path.stem}.mid"


class Req(BaseModel):
    audio_path: str
    out_dir: str


@app.get("/health")
def health() -> dict:
    return {"ok": True, "device": DEVICE, "loaded": _model is not None}


@app.post("/transcribe")
def run(req: Req) -> dict:
    audio = Path(req.audio_path)
    if not audio.exists():
        raise HTTPException(404, f"Audio not found: {audio}")
    t = time.time()
    try:
        midi = transcribe(audio, Path(req.out_dir))
    except Exception as e:
        raise HTTPException(500, f"YourMT3+ failed: {e}")
    return {"midi_path": str(midi), "seconds": round(time.time() - t, 1), "device": DEVICE}


@app.on_event("startup")
def _warm() -> None:
    threading.Thread(target=model, daemon=True).start()
