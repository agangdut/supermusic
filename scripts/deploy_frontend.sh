#!/usr/bin/env bash
# Deploy/build the Next.js frontend.
# Modes:
#   - Default: local production build (npm ci && npm run build && npm run start)
#   - --export: static export to ./out (good for GitHub Pages)
#   - --pages DIR: copy the export to DIR (e.g., ../docs for Pages)
#   - --vercel: deploy with Vercel if VERCEL_TOKEN is set

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
MODE="local"
PAGES_DIR=""
while [[ "${1:-}" != "" ]]; do
  case "$1" in
    --export) MODE="export";;
    --pages) shift; PAGES_DIR="${1:-}"; MODE="export";;
    --vercel) MODE="vercel";;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
  shift || true
done

echo "==> Frontend dir: $FRONTEND_DIR"
cd "$FRONTEND_DIR"

if ! command -v node >/dev/null 2>&1; then
  echo "Error: Node.js not found. Install Node 18+." >&2; exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm not found." >&2; exit 1
fi

# Install deps (clean, reproducible)
echo "==> Installing dependencies (npm ci)"
npm ci

case "$MODE" in
  local)
    echo "==> Building Next.js (production)"
    npm run build
    echo "==> Starting Next.js server"
    # Uses PORT if provided, otherwise 3000
    PORT="${PORT:-3000}" npm run start
    ;;

  export)
    echo "==> Building Next.js"
    npm run build
    echo "==> Exporting static site to ./out"
    # Requires "next export" to be configured (works with pages router, and most app router sites if set up)
    npx next export

    if [[ -n "$PAGES_DIR" ]]; then
      echo "==> Copying ./out to $PAGES_DIR"
      mkdir -p "$PAGES_DIR"
      # Remove existing files except .git (if any)
      find "$PAGES_DIR" -mindepth 1 -maxdepth 1 ! -name ".git" -exec rm -rf {} +
      cp -R out/* "$PAGES_DIR"/
      echo "==> Copied export to $PAGES_DIR (commit & push to deploy via GitHub Pages)"
    else
      echo "==> Static site available in $FRONTEND_DIR/out"
    fi
    ;;

  vercel)
    if ! command -v vercel >/dev/null 2>&1; then
      echo "==> Installing vercel CLI locally"
      npm i -D vercel
      npx vercel --version >/dev/null
      VC="npx vercel"
    else
      VC="vercel"
    fi
    if [[ -z "${VERCEL_TOKEN:-}" ]]; then
      echo "Error: VERCEL_TOKEN not set. Export it and rerun with --vercel." >&2; exit 1
    fi
    echo "==> Deploying with Vercel"
    $VC --token "$VERCEL_TOKEN" --prod
    ;;

  *)
    echo "Unknown MODE: $MODE"; exit 1;;
esac

echo "==> Frontend deploy script finished."
