# MuScriptor multi-instrument transcription (Kyutai + Mirelo, 2026), on the GPU when available.
# Weights are CC BY-NC 4.0 and gated on Hugging Face: accept the licence on
# https://huggingface.co/MuScriptor/muscriptor-medium and put HF_TOKEN in .env.
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 && rm -rf /var/lib/apt/lists/*

# torch comes from the base image; the rest from PyPI
RUN --mount=type=cache,target=/root/.cache/pip pip install --default-timeout=300 \
    "muscriptor==0.3.0" pretty_midi "fastapi" "uvicorn[standard]"

WORKDIR /srv
COPY server.py /srv/server.py

EXPOSE 8200
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8200"]
