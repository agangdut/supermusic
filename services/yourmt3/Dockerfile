# YourMT3+ multi-instrument transcription, on the GPU when one is available.
# transformers is pinned to 4.40: newer T5 code expects a cache_position YourMT3 never passes.
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/pip pip install --default-timeout=300 \
    "lightning==2.5.0" "transformers==4.40.2" einops deprecated librosa mido pretty_midi mir_eval \
    matplotlib soundfile scipy scikit-learn pyyaml requests tqdm torchmetrics smart-open \
    "torchaudio==2.5.1" "pytorch_lightning==2.5.0" wandb fastapi "uvicorn[standard]"

WORKDIR /srv
COPY . /srv
# Checkpoints live in the shared data volume so they survive rebuilds
RUN mkdir -p /app/data/models/yourmt3/logs && ln -s /app/data/models/yourmt3/logs /srv/amt/logs

EXPOSE 8100
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8100"]
