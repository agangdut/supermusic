"""
Small HTTP wrapper around LAION CLAP so the main backend can describe songs
by how they sound, and search them by a typed description.

POST /embed/audio  (raw audio file bytes, any format ffmpeg reads)
  -> {"vector": [512 floats]}   one unit-length vector for the whole clip
POST /embed/text   {"texts": ["sad slow piano ballad", ...]}
  -> {"vectors": [[512 floats], ...]}

The song vector is the average of up to six evenly spaced 10-second windows,
skipping silent ones: one description of what the song sounds like overall
(see docs/embedding-comparison.md). The model downloads once into the data
volume on the first request.
"""
from __future__ import annotations

import os
import tempfile
import threading
from typing import List

import numpy as np
import torch
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

MODEL = os.getenv("CLAP_MODEL", "laion/clap-htsat-unfused")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
SR = 48000
WINDOW_S = 10.0
MAX_WINDOWS = 6

app = FastAPI(title="CLAP")
_model = None
_proc = None
_lock = threading.Lock()


def model():
    global _model, _proc
    with _lock:
        if _model is None:
            from transformers import ClapModel, ClapProcessor

            _proc = ClapProcessor.from_pretrained(MODEL)
            _model = ClapModel.from_pretrained(MODEL).to(DEVICE).eval()
        return _model, _proc


def _tensor(out):
    """get_*_features returns a tensor, or an output object in newer transformers."""
    for attr in ("audio_embeds", "text_embeds", "pooler_output"):
        if getattr(out, attr, None) is not None:
            return getattr(out, attr)
    return out


def windows(y: np.ndarray) -> List[np.ndarray]:
    n = int(WINDOW_S * SR)
    if len(y) <= n:
        return [y]
    starts = np.linspace(0, len(y) - n, num=min(MAX_WINDOWS, max(1, len(y) // n))).astype(int)
    wins = [y[s:s + n] for s in starts]
    loud = [w for w in wins if np.sqrt(np.mean(w ** 2)) > 1e-3]
    return loud or wins[:1]


@app.get("/health")
def health():
    return {"loaded": _model is not None, "device": DEVICE, "model": MODEL}


@app.post("/embed/audio")
async def embed_audio(request: Request):
    import librosa

    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="Send the audio file as the request body.")
    # A temp file lets librosa fall back to ffmpeg for MP3/M4A
    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as f:
        f.write(data)
        path = f.name
    try:
        y, _ = librosa.load(path, sr=SR, mono=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Couldn't decode that audio: {e}")
    finally:
        os.unlink(path)
    if len(y) < SR:
        raise HTTPException(status_code=400, detail="Audio is shorter than a second.")
    m, proc = model()
    with torch.no_grad():
        x = proc(audio=windows(y), sampling_rate=SR, return_tensors="pt").to(DEVICE)
        e = torch.nn.functional.normalize(_tensor(m.get_audio_features(**x)), dim=-1).mean(dim=0)
        e = torch.nn.functional.normalize(e, dim=-1)
    return {"vector": [round(float(v), 5) for v in e.cpu()]}


class TextReq(BaseModel):
    texts: List[str]


@app.post("/embed/text")
def embed_text(req: TextReq):
    if not req.texts:
        raise HTTPException(status_code=400, detail="Send at least one text.")
    m, proc = model()
    with torch.no_grad():
        x = proc(text=req.texts, return_tensors="pt", padding=True).to(DEVICE)
        e = torch.nn.functional.normalize(_tensor(m.get_text_features(**x)), dim=-1)
    return {"vectors": [[round(float(v), 5) for v in row] for row in e.cpu()]}
