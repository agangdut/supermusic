FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fluidsynth \
    fluid-soundfont-gm \
    && if [ "$(uname -m)" = "aarch64" ]; then apt-get install -y build-essential; fi \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt ./

# Install Python dependencies. CPU-only torch first, so demucs doesn't pull
# several GB of CUDA wheels.
RUN --mount=type=cache,target=/root/.cache/pip pip install --default-timeout=300 --retries 10 torch torchaudio --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple
# On ARM (Apple Silicon Macs, Snapdragon PCs) demucs' sphn dependency has no
# prebuilt wheel, so pip compiles it: that needs the C compiler installed above,
# and this setting lets its bundled Opus library build with CMake 4.
ENV CMAKE_POLICY_VERSION_MINIMUM=3.5
RUN --mount=type=cache,target=/root/.cache/pip pip install --default-timeout=300 --retries 10 -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY scripts/ ./scripts/

# Create necessary directories
RUN mkdir -p data/raw data/interim data/processed data/samples static

# Environment variables
ENV PYTHONPATH=/app:/app/backend
ENV SM_DATA_DIR=/app/data
ENV SM_RAW_DIR=/app/data/raw
ENV SM_INTERIM_DIR=/app/data/interim
ENV SM_PROCESSED_DIR=/app/data/processed

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]

