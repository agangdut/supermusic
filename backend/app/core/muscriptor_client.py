"""
Client for the MuScriptor service (services/muscriptor), a multi-instrument
transcriber from 2026 trained on far more real recordings than YourMT3+.
Runs in its own container, on the GPU when there is one, and writes a
multi-track MIDI with an instrument per track.
"""
from __future__ import annotations

import json
import os
import shutil
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from app.core.config import settings

URL = os.getenv("MUSCRIPTOR_URL", "http://muscriptor:8200")


def available() -> bool:
    """Running, and able to load its model (already loaded, or has a Hugging Face token)."""
    try:
        with urllib.request.urlopen(f"{URL}/health", timeout=3) as r:
            h = json.loads(r.read())
            return bool(h.get("loaded") or h.get("token"))
    except Exception:
        return False


def _call(method: str, path: str, body: dict | None = None, timeout: float = 30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{URL}{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(json.loads(e.read() or b"{}").get("detail", f"MuScriptor error {e.code}"))
    except urllib.error.URLError:
        raise RuntimeError("The MuScriptor service isn't running. Start it with: docker compose up -d muscriptor")


def _fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m} min {s:02d} s" if m else f"{s} s"


def transcribe_muscriptor(audio_path: str | Path, out_dir: Path | None = None, instruments: list | None = None,
                          fast: bool | None = None, beam_size: int = 1, dynamics: bool = True,
                          label: str = "MuScriptor") -> Path:
    """Run MuScriptor and show live progress: it works through the song in 5-second sections.

    `instruments` limits which instruments it may write (names like "electric_bass", "voice");
    `fast` batches sections for speed; `dynamics` shapes note loudness to follow the audio."""
    from app.core.progress import report_detail

    audio_path = Path(audio_path)
    out_dir = (out_dir or (settings.PROCESSED_DIR / "midi")) / uuid.uuid4().hex
    job = _call("POST", "/jobs", {"audio_path": str(audio_path.resolve()), "out_dir": str(out_dir),
                                  "instruments": instruments, "fast": fast, "beam_size": beam_size})
    deadline = time.time() + 3 * 3600
    while time.time() < deadline:
        st = _call("GET", f"/jobs/{job['id']}")
        if st["status"] == "done":
            break
        if st["status"] == "error":
            raise RuntimeError(st.get("error") or "MuScriptor failed")
        cpu = " on the CPU, which is slow" if st.get("device") == "cpu" else ""
        if not st.get("total"):
            doing = {"loading": "loading the model (the very first run also downloads it)",
                     "waiting": "waiting for another song to finish"}.get(st["status"], "getting the audio ready")
            report_detail(f"{label}: {doing}{cpu}…")
        else:
            done, total = st["completed"], st["total"]
            left = st.get("remaining_s")
            eta = f", about {_fmt(left)} left" if left and done else ""
            report_detail(f"{label}{cpu}: section {done} of {total} ({round(100 * done / total)}%){eta}",
                          fraction=done / total, remaining_s=left if done else None)
        time.sleep(2)
    else:
        raise RuntimeError("MuScriptor took more than 3 hours; giving up")
    midi = Path(st["midi_path"])
    final = out_dir / f"{audio_path.stem}.mid"
    if midi != final:
        shutil.move(str(midi), final)
    # MuScriptor writes every note equally loud; follow the song's loudness instead
    # (quiet verses, loud choruses, melody over accompaniment) and pedal the piano parts
    if dynamics:
        from app.core.humanize import humanize

        report_detail("Shaping the dynamics to follow the song…")
        humanize(final, audio_path)
    return final


REF_URL = os.getenv("MUSCRIPTOR_REF_URL", "http://muscriptor_ref:8222")


def transcribe_muscriptor_ref(audio_path: str | Path, out_dir: Path | None = None,
                              detect_tempo: bool = True) -> Path:
    """Run the official MuScriptor server (the `muscriptor_ref` service) on the same audio,
    for checking our wrapper against it. Not used by the app.

    Its MIDI has every note pushed later by a whole number of bars so that bar 1 lands on
    the first downbeat (it records the amount in a marker). That shift is taken back out
    here so the notes line up with the audio again. Its other timing fix, moving every
    note earlier by the model's small measured lag (up to ~25 ms), is kept; pass
    `detect_tempo=False` to turn that off too and get the model's raw note times."""
    import mido
    import pretty_midi

    audio_path = Path(audio_path)
    out_dir = (out_dir or (settings.PROCESSED_DIR / "midi")) / uuid.uuid4().hex
    out_dir.mkdir(parents=True, exist_ok=True)
    boundary = uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="detect_tempo"\r\n\r\n'
             f'{"best-effort" if detect_tempo else "false"}\r\n'.encode(),
             f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{audio_path.name}"\r\n'
             f'Content-Type: application/octet-stream\r\n\r\n'.encode(),
             audio_path.read_bytes(), f"\r\n--{boundary}--\r\n".encode()]
    req = urllib.request.Request(f"{REF_URL}/transcribe/midi", data=b"".join(parts), method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=3 * 3600) as r:
            midi_bytes = r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Official MuScriptor error {e.code}: {e.read()[:300].decode(errors='replace')}")
    except urllib.error.URLError:
        raise RuntimeError("The official MuScriptor service isn't running. Start it with: "
                           "docker compose --profile ref up -d muscriptor_ref")
    raw = out_dir / f"{audio_path.stem}.official.mid"  # exactly what the server sent
    raw.write_bytes(midi_bytes)

    shift = 0.0
    for msg in mido.MidiFile(str(raw)).tracks[0]:
        if msg.type == "marker" and msg.text.startswith("muscriptor:bar_offset="):
            shift = float(msg.text.split("=", 1)[1])
    pm = pretty_midi.PrettyMIDI(str(raw))
    for inst in pm.instruments:
        for n in inst.notes:
            n.start, n.end = max(0.0, n.start - shift), max(0.0, n.end - shift)
    final = out_dir / f"{audio_path.stem}.mid"
    pm.write(str(final))
    return final
