#!/usr/bin/env bash
# Deploy/run the FastAPI backend.
# Modes:
#   - Default: Python venv, install, run with uvicorn
#   - --docker: Build and run via Docker (if Docker is installed)
# Env:
#   - APP_MODULE (default: app.main:app)
#   - HOST (default: 0.0.0.0)
#   - PORT (default: 8000)
#   - ENV_FILE (optional: path to .env)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
APP_MODULE="${APP_MODULE:-app.main:app}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
MODE="venv"

while [[ "${1:-}" != "" ]]; do
  case "$1" in
    --docker) MODE="docker";;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
  shift || true
done

if [[ -n "${ENV_FILE:-}" && -f "$ENV_FILE" ]]; then
  echo "==> Loading env from $ENV_FILE"
  # shellcheck disable=SC2046
  export $(grep -v '^#' "$ENV_FILE" | xargs -I {} echo {})
fi

echo "==> Backend dir: $BACKEND_DIR"
cd "$BACKEND_DIR"

if [[ "$MODE" == "docker" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "Error: Docker not found. Install Docker or run without --docker." >&2; exit 1
  fi

  DOCKER_IMAGE="${DOCKER_IMAGE:-supermusic-backend:latest}"
  echo "==> Building Docker image: $DOCKER_IMAGE"
  cat > Dockerfile <<'EOF'
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

  docker build -t "$DOCKER_IMAGE" .
  echo "==> Running container on port $PORT"
  docker run --rm -p "$PORT:8000" --env-file "${ENV_FILE:-/dev/null}" "$DOCKER_IMAGE"
  exit 0
fi

# ---- VENV path ----
VENV_DIR="${VENV_DIR:-.venv}"
PY_BIN="${PY_BIN:-python3}"

if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "Error: $PY_BIN not found. Set PY_BIN to your Python 3.10/3.11 executable." >&2; exit 1
fi

echo "==> Creating venv: $VENV_DIR (if missing)"
"$PY_BIN" -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "==> Upgrading pip"
python -m pip install --upgrade pip

echo "==> Installing backend requirements"
pip install -r requirements.txt

# Optional: run migrations or data prep hooks here
if [[ -f "app/hooks/prestart.sh" ]]; then
  echo "==> Running prestart hook"
  bash app/hooks/prestart.sh
fi

echo "==> Starting FastAPI with uvicorn ($APP_MODULE) on $HOST:$PORT"
exec uvicorn "$APP_MODULE" --host "$HOST" --port "$PORT"
