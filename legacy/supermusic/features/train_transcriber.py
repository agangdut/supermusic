#!/usr/bin/env python3
"""
train_transcriber.py — Minimal Onsets & Frames–style trainer (PyTorch)
=====================================================================
Trains a simple audio→MIDI transcriber on paired (WAV, MIDI) files using GPU.

Expected data layout (pairs directory):
    <pairs_dir>/...
        song1.wav
        song1.mid            # or .midi / .musicxml (parsed via music21/pretty_midi)
        song2.wav
        song2.mid
        ...

Notes
-----
• This is a *starter* trainer aimed at lofi piano/hooks. It implements:
  - Mel feature frontend (librosa)
  - Convolutional + BiLSTM backbone
  - Two heads: onset and frame (BCE losses)
  - Mixed-precision training (AMP) and grad clipping
  - Simple frame-level F1 for onsets (for quick sanity checks)

• For best results, create synthetic paired data by rendering MIDI→WAV (perfect alignment),
  then mix in aligned YouTube audio.

Dependencies
------------
python 3.10+, pytorch, librosa, soundfile, pretty_midi, numpy

Install (Windows, CUDA 12.1 wheels):
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
    pip install numpy<2.0 librosa soundfile pretty_midi music21 mido

Run
---
    python train_transcriber.py \
        --pairs-dir D:/datasets/lofi_pairs_synth \
        --save-dir  D:/models/lofi_of \
        --epochs 20 --batch-size 8 --chunk-secs 10

After training, the checkpoint can be loaded in your inference script to replace the backend.
"""
from __future__ import annotations

import argparse
import json
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Feature extraction
import librosa
import numpy as np
import pretty_midi
import soundfile as sf
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset, random_split

# ---------------------------
# Utilities
# ---------------------------


def seed_everything(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def list_pairs(pairs_dir: Path) -> List[Tuple[Path, Path]]:
    wavs = []
    for fp in pairs_dir.rglob("*.wav"):
        stem = fp.stem
        for ext in (".mid", ".midi", ".musicxml", ".xml"):
            cand = fp.with_suffix(ext)
            if cand.exists():
                wavs.append((fp, cand))
                break
    return sorted(wavs)


@dataclass
class TrainConfig:
    pairs_dir: Path
    save_dir: Path
    sr: int = 22050
    hop_length: int = 256
    n_mels: int = 96
    fmin: int = 30
    fmax: int = 8000
    chunk_secs: float = 10.0
    min_midi: int = 21
    max_midi: int = 108
    val_split: float = 0.1
    batch_size: int = 8
    epochs: int = 10
    lr: float = 1e-3
    num_workers: int = 4
    device: str = "cuda"
    amp: bool = True
    onset_weight: float = 1.0
    frame_weight: float = 0.5


# ---------------------------
# Dataset
# ---------------------------
class PairDataset(Dataset):
    def __init__(self, pairs: List[Tuple[Path, Path]], cfg: TrainConfig):
        self.pairs = pairs
        self.cfg = cfg
        self.pitch_count = cfg.max_midi - cfg.min_midi + 1

    def __len__(self):
        return len(self.pairs)

    def _load_audio(self, wav_path: Path) -> np.ndarray:
        y, sr = sf.read(str(wav_path), always_2d=False)
        if y.ndim == 2:
            y = y.mean(axis=1)
        if sr != self.cfg.sr:
            y = librosa.resample(y, orig_sr=sr, target_sr=self.cfg.sr)
        # normalize
        if np.max(np.abs(y)) > 0:
            y = y / np.max(np.abs(y))
        return y.astype(np.float32)

    def _melspec(self, y: np.ndarray) -> np.ndarray:
        S = librosa.feature.melspectrogram(
            y=y,
            sr=self.cfg.sr,
            n_fft=2048,
            hop_length=self.cfg.hop_length,
            n_mels=self.cfg.n_mels,
            fmin=self.cfg.fmin,
            fmax=self.cfg.fmax,
            power=2.0,
        )
        S = librosa.power_to_db(S, ref=np.max)
        # normalize to ~[0,1]
        S = (S - S.min()) / max(1e-6, (S.max() - S.min()))
        return S.astype(np.float32)  # [n_mels, T]

    def _make_targets(self, midi_path: Path, T: int) -> Tuple[np.ndarray, np.ndarray]:
        """Return (onset[T, P], frame[T, P]) with P pitches in [min_midi, max_midi]."""
        pm = pretty_midi.PrettyMIDI(str(midi_path))
        onset = np.zeros((T, self.pitch_count), dtype=np.float32)
        frame = np.zeros((T, self.pitch_count), dtype=np.float32)
        hop = self.cfg.hop_length / self.cfg.sr
        for inst in pm.instruments:
            for n in inst.notes:
                p = int(n.pitch) - self.cfg.min_midi
                if p < 0 or p >= self.pitch_count:
                    continue
                t_on = max(0.0, n.start)
                t_off = max(t_on + 1e-3, n.end)
                i_on = int(np.floor(t_on / hop))
                i_off = int(np.ceil(t_off / hop))
                i_on = np.clip(i_on, 0, T - 1)
                i_off = np.clip(i_off, 0, T)
                onset[i_on, p] = 1.0
                frame[i_on:i_off, p] = 1.0
        return onset, frame

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        wav_path, midi_path = self.pairs[idx]
        y = self._load_audio(wav_path)
        # sample a chunk
        total_secs = len(y) / self.cfg.sr
        chunk = int(self.cfg.chunk_secs * self.cfg.sr)
        if total_secs <= self.cfg.chunk_secs:
            y_chunk = y
        else:
            start = random.randint(0, len(y) - chunk)
            y_chunk = y[start : start + chunk]
        mel = self._melspec(y_chunk)  # [M, T]
        T = mel.shape[1]
        # For synthetic renders, MIDI aligns 1:1; for real audio, this is an approximation
        onset, frame = self._make_targets(midi_path, T)
        sample = {
            "mel": torch.from_numpy(mel),  # [M, T]
            "onset": torch.from_numpy(onset),  # [T, P]
            "frame": torch.from_numpy(frame),  # [T, P]
        }
        return sample


def collate_fn(batch: List[Dict[str, torch.Tensor]]) -> Dict[str, torch.Tensor]:
    # Pad to max-T in batch (time dimension)
    M = batch[0]["mel"].shape[0]
    P = batch[0]["onset"].shape[1]
    T_max = max(x["mel"].shape[1] for x in batch)

    def pad_time(x, T_target, dim=-1):
        pad = T_target - x.shape[dim]
        if pad <= 0:
            return x
        pad_dims = [(0, 0)] * x.ndim
        pad_dims[dim] = (0, pad)
        pad_dims = sum(pad_dims[::-1], ())  # convert to torch.nn.functional.pad format
        return torch.nn.functional.pad(x, pad_dims)

    mels = torch.stack(
        [pad_time(b["mel"], T_max, dim=1) for b in batch], dim=0
    )  # [B,M,T]
    onsets = torch.stack(
        [pad_time(b["onset"], T_max, dim=0) for b in batch], dim=0
    )  # [B,T,P]
    frames = torch.stack(
        [pad_time(b["frame"], T_max, dim=0) for b in batch], dim=0
    )  # [B,T,P]
    return {"mel": mels, "onset": onsets, "frame": frames}


# ---------------------------
# Model
# ---------------------------
class ConvBLSTM(nn.Module):
    def __init__(
        self,
        n_mels: int,
        n_pitches: int,
        conv_channels: int = 64,
        lstm_hidden: int = 128,
        lstm_layers: int = 2,
    ):
        super().__init__()
        self.frontend = nn.Sequential(
            nn.Conv2d(
                1, conv_channels, kernel_size=(5, 5), padding=(2, 2), stride=(1, 1)
            ),
            nn.BatchNorm2d(conv_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(
                conv_channels,
                conv_channels,
                kernel_size=(3, 3),
                padding=(1, 1),
                stride=(1, 1),
            ),
            nn.BatchNorm2d(conv_channels),
            nn.ReLU(inplace=True),
        )
        self.proj = nn.Conv2d(
            conv_channels, 128, kernel_size=(n_mels, 1)
        )  # collapse mel dim
        self.blstm = nn.LSTM(
            input_size=128,
            hidden_size=lstm_hidden,
            num_layers=lstm_layers,
            batch_first=True,
            bidirectional=True,
        )
        feat = lstm_hidden * 2
        self.head_onset = nn.Linear(feat, n_pitches)
        self.head_frame = nn.Linear(feat, n_pitches)

    def forward(self, mel: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        # mel: [B,M,T] -> [B,1,M,T]
        x = mel.unsqueeze(1)
        x = self.frontend(x)  # [B,C,M,T]
        x = self.proj(x)  # [B,128,1,T]
        x = x.squeeze(2).transpose(1, 2)  # [B,T,128]
        x, _ = self.blstm(x)  # [B,T,2H]
        onset = self.head_onset(x)  # [B,T,P]
        frame = self.head_frame(x)  # [B,T,P]
        return onset, frame


# ---------------------------
# Metrics
# ---------------------------
@torch.no_grad()
def f1_onsets(
    pred_logits: torch.Tensor, target: torch.Tensor, thresh: float = 0.5
) -> Tuple[float, float, float]:
    """Simple frame-level onset F1 across batch (not note-level)."""
    pred = (torch.sigmoid(pred_logits) >= thresh).float()
    tp = (pred * target).sum().item()
    fp = (pred * (1 - target)).sum().item()
    fn = ((1 - pred) * target).sum().item()
    precision = tp / (tp + fp + 1e-8)
    recall = tp / (tp + fn + 1e-8)
    f1 = 2 * precision * recall / (precision + recall + 1e-8)
    return precision, recall, f1


# ---------------------------
# Training
# ---------------------------


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    optim: torch.optim.Optimizer,
    device: str,
    onset_w: float,
    frame_w: float,
    scaler: torch.cuda.amp.GradScaler,
    amp_enabled: bool,
) -> Dict[str, float]:
    model.train()
    loss_onset_fn = nn.BCEWithLogitsLoss()
    loss_frame_fn = nn.BCEWithLogitsLoss()
    total, losss, f1s = 0, 0.0, 0.0
    for batch in loader:
        mel = batch["mel"].to(device, non_blocking=True)
        onset_t = batch["onset"].to(device, non_blocking=True)
        frame_t = batch["frame"].to(device, non_blocking=True)
        optim.zero_grad(set_to_none=True)
        with torch.cuda.amp.autocast(enabled=amp_enabled):
            onset_p, frame_p = model(mel)
            loss_on = loss_onset_fn(onset_p, onset_t)
            loss_fr = loss_frame_fn(frame_p, frame_t)
            loss = onset_w * loss_on + frame_w * loss_fr
        scaler.scale(loss).backward()
        # optional grad clip
        scaler.unscale_(optim)
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        scaler.step(optim)
        scaler.update()
        # metrics
        _, _, f1 = f1_onsets(onset_p.detach(), onset_t.detach())
        losss += loss.item()
        f1s += f1
        total += 1
    return {"loss": losss / max(1, total), "f1_onset": f1s / max(1, total)}


@torch.no_grad()
def validate(
    model: nn.Module, loader: DataLoader, device: str, amp_enabled: bool
) -> Dict[str, float]:
    model.eval()
    loss_onset_fn = nn.BCEWithLogitsLoss()
    loss_frame_fn = nn.BCEWithLogitsLoss()
    total, losss, f1s = 0, 0.0, 0.0
    for batch in loader:
        mel = batch["mel"].to(device, non_blocking=True)
        onset_t = batch["onset"].to(device, non_blocking=True)
        frame_t = batch["frame"].to(device, non_blocking=True)
        with torch.cuda.amp.autocast(enabled=amp_enabled):
            onset_p, frame_p = model(mel)
            loss_on = loss_onset_fn(onset_p, onset_t)
            loss_fr = loss_frame_fn(frame_p, frame_t)
            loss = loss_on + 0.5 * loss_fr
        _, _, f1 = f1_onsets(onset_p, onset_t)
        losss += loss.item()
        f1s += f1
        total += 1
    return {"loss": losss / max(1, total), "f1_onset": f1s / max(1, total)}


# ---------------------------
# Main
# ---------------------------


def main():
    ap = argparse.ArgumentParser(description="Train a simple Onsets&Frames transcriber")
    ap.add_argument(
        "--pairs-dir",
        type=str,
        required=True,
        help="Directory containing WAV/MIDI pairs",
    )
    ap.add_argument(
        "--save-dir", type=str, required=True, help="Where to save checkpoints"
    )
    ap.add_argument("--sr", type=int, default=22050)
    ap.add_argument("--hop-length", type=int, default=256)
    ap.add_argument("--n-mels", type=int, default=96)
    ap.add_argument("--fmin", type=int, default=30)
    ap.add_argument("--fmax", type=int, default=8000)
    ap.add_argument("--chunk-secs", type=float, default=10.0)
    ap.add_argument("--min-midi", type=int, default=21)
    ap.add_argument("--max-midi", type=int, default=108)
    ap.add_argument("--val-split", type=float, default=0.1)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--num-workers", type=int, default=4)
    ap.add_argument("--device", type=str, default="cuda")
    ap.add_argument("--no-amp", action="store_true", help="Disable AMP mixed precision")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--save-every", type=int, default=1)
    args = ap.parse_args()

    cfg = TrainConfig(
        pairs_dir=Path(args.pairs_dir),
        save_dir=Path(args.save_dir),
        sr=args.sr,
        hop_length=args.hop_length,
        n_mels=args.n_mels,
        fmin=args.fmin,
        fmax=args.fmax,
        chunk_secs=args.chunk_secs,
        min_midi=args.min_midi,
        max_midi=args.max_midi,
        val_split=args.val_split,
        batch_size=args.batch_size,
        epochs=args.epochs,
        lr=args.lr,
        num_workers=args.num_workers,
        device=args.device,
        amp=not args.no_amp,
    )

    seed_everything(args.seed)
    cfg.save_dir.mkdir(parents=True, exist_ok=True)

    pairs = list_pairs(cfg.pairs_dir)
    if not pairs:
        raise SystemExit(f"No (wav, midi) pairs found under {cfg.pairs_dir}")
    n_total = len(pairs)
    n_val = max(1, int(np.ceil(cfg.val_split * n_total)))
    n_train = max(1, n_total - n_val)
    train_pairs = pairs[:n_train]
    val_pairs = pairs[n_train:]

    train_ds = PairDataset(train_pairs, cfg)
    val_ds = PairDataset(val_pairs, cfg)

    train_loader = DataLoader(
        train_ds,
        batch_size=cfg.batch_size,
        shuffle=True,
        num_workers=cfg.num_workers,
        pin_memory=True,
        collate_fn=collate_fn,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=cfg.batch_size,
        shuffle=False,
        num_workers=cfg.num_workers,
        pin_memory=True,
        collate_fn=collate_fn,
    )

    n_pitches = cfg.max_midi - cfg.min_midi + 1
    model = ConvBLSTM(cfg.n_mels, n_pitches).to(cfg.device)

    optim = torch.optim.AdamW(model.parameters(), lr=cfg.lr)
    scaler = torch.cuda.amp.GradScaler(
        enabled=cfg.amp
        and (cfg.device.startswith("cuda") and torch.cuda.is_available())
    )

    best_val_f1 = -1.0

    # Save config
    with open(cfg.save_dir / "config.json", "w") as f:
        json.dump(cfg.__dict__, f, indent=2, default=str)

    for epoch in range(1, cfg.epochs + 1):
        tr = train_one_epoch(
            model,
            train_loader,
            optim,
            cfg.device,
            cfg.onset_weight,
            cfg.frame_weight,
            scaler,
            cfg.amp,
        )
        va = validate(model, val_loader, cfg.device, cfg.amp)
        print(
            f"Epoch {epoch:02d} | train loss {tr['loss']:.4f} f1_on {tr['f1_onset']:.3f} | val loss {va['loss']:.4f} f1_on {va['f1_onset']:.3f}"
        )

        # Save periodic
        if epoch % args.save_every == 0:
            ckpt_path = cfg.save_dir / f"epoch_{epoch:03d}.pt"
            torch.save(
                {
                    "epoch": epoch,
                    "model_state": model.state_dict(),
                    "optim_state": optim.state_dict(),
                    "scaler_state": scaler.state_dict(),
                    "config": cfg.__dict__,
                },
                ckpt_path,
            )

        # Save best by val F1
        if va["f1_onset"] > best_val_f1:
            best_val_f1 = va["f1_onset"]
            best_path = cfg.save_dir / "best.pt"
            torch.save(
                {
                    "epoch": epoch,
                    "model_state": model.state_dict(),
                    "optim_state": optim.state_dict(),
                    "scaler_state": scaler.state_dict(),
                    "config": cfg.__dict__,
                },
                best_path,
            )


if __name__ == "__main__":
    main()
