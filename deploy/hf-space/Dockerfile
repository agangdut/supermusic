# The SuperMusic API as a Hugging Face Space (Docker SDK). Same as the root Dockerfile,
# without BuildKit cache mounts, listening on 7860 and writable by the Space's user (uid 1000).
# .github/workflows/hf-space.yml copies this next to backend/, scripts/ and requirements.txt.
FROM python:3.10-slim

RUN apt-get update && apt-get install -y ffmpeg fluidsynth fluid-soundfont-gm \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --default-timeout=300 torch torchaudio \
      --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple \
 && pip install --no-cache-dir --default-timeout=300 -r requirements.txt

COPY backend/ ./backend/
COPY scripts/ ./scripts/
RUN mkdir -p data/raw data/interim data/processed data/samples data/artifacts static \
 && chown -R user:user /app

USER user
ENV HOME=/home/user \
    PYTHONPATH=/app:/app/backend \
    SM_DATA_DIR=/app/data \
    SM_RAW_DIR=/app/data/raw \
    SM_INTERIM_DIR=/app/data/interim \
    SM_PROCESSED_DIR=/app/data/processed \
    SUPERMUSIC_ARTIFACT_DIR=/app/data/artifacts \
    TORCH_HOME=/app/data/models/torch \
    HF_HOME=/app/data/models/hf

EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "7860"]
