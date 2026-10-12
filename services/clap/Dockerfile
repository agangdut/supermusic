# CLAP audio/text embeddings (LAION clap-htsat-unfused) for the Music Map's "sound" feature
# and describe-a-vibe search. Small model: runs fine on the CPU, faster on the GPU.
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 && rm -rf /var/lib/apt/lists/*

# torch comes from the base image; the rest from PyPI
RUN --mount=type=cache,target=/root/.cache/pip pip install --default-timeout=300 \
    "transformers>=4.38,<5" librosa soundfile "fastapi" "uvicorn[standard]"

WORKDIR /srv
COPY server.py /srv/server.py

EXPOSE 8300
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8300"]
