# GAME (Generative Adaptive MIDI Extractor, OpenVPI, 2026): turns singing into notes.
# Code MIT; model weights CC BY-NC-SA 4.0 (non-commercial), downloaded on first use.
# All four GPU services use the same base image, so Docker downloads and stores it once.
FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 git && rm -rf /var/lib/apt/lists/*

ARG GAME_COMMIT=f4239345f0fed21890d362c74a35fd857724aa82
RUN git clone https://github.com/openvpi/GAME /opt/game && git -C /opt/game checkout $GAME_COMMIT && rm -rf /opt/game/.git

RUN --mount=type=cache,target=/root/.cache/pip pip install --default-timeout=300 \
    click colorednoise "einops>=0.7.0" h5py librosa lightning loguru matplotlib mido "numpy<2.0.0" \
    omegaconf "pydantic>=2.11,<3.0" resampy "scipy>=1.10.0" sympy torchmetrics tqdm pretty_midi \
    fastapi "uvicorn[standard]"
# Demucs too, so the voice can be separated on the GPU (the backend only has a CPU).
# Demucs 4.1 needs only torch>=2.1, which the base image's CUDA build already satisfies.
RUN --mount=type=cache,target=/root/.cache/pip pip install --default-timeout=300 "demucs>=4.1" soundfile

WORKDIR /srv
COPY server.py /srv/server.py

EXPOSE 8300
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8300"]
