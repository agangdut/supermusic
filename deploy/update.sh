#!/usr/bin/env bash
# Update the live site without stopping anyone's job.
#
#   ./deploy/update.sh          # pull, build, then restart once running jobs are done
#   ./deploy/update.sh --now    # don't wait: jobs still running stop (they can be started again)
#
# What it does, in order:
#   1. git pull, then build the new images while the old site keeps running.
#   2. Puts the new website live. People who open the site from now on get the new
#      pages; anyone already on it keeps their page until they reload or move on.
#   3. Pauses new jobs (they're told "the site is updating, try again in a minute")
#      and waits for the jobs already waiting or running to finish.
#   4. Swaps in the new backend (a few seconds) and lets jobs start again.
#
# If the jobs take longer than MAX_WAIT_MINUTES (60), it gives up, lets jobs start
# again and leaves the old backend running. Run it again later, or with --now.
#
# Everything is in main(), so a `git pull` that changes this file doesn't confuse
# the copy that's already running.
set -euo pipefail

main() {
  cd "$(dirname "$0")/.."
  local compose=(docker compose -f docker-compose.prod.yml)
  local max_wait=$(( ${MAX_WAIT_MINUTES:-60} * 60 ))
  local now=0
  [[ "${1:-}" == "--now" ]] && now=1

  in_backend() { "${compose[@]}" exec -T backend python -c "$1" 2>/dev/null; }
  pause()  { in_backend "open('/app/data/updating', 'w').close()" || true; }
  resume() {
    # Try for a minute: right after a swap the new backend may still be starting
    local i
    for i in $(seq 12); do
      in_backend "import os; os.path.exists('/app/data/updating') and os.remove('/app/data/updating')" && return 0
      rm -f data/updating 2>/dev/null && [[ ! -e data/updating ]] && return 0
      sleep 5
    done
    echo "!!  Couldn't lift the pause on new jobs. Remove data/updating by hand (it also expires by itself after 3 hours)."
  }
  busy()   { in_backend "import json, urllib.request; print(json.load(urllib.request.urlopen('http://localhost:8000/healthz/jobs', timeout=10))['busy'])"; }

  echo "==> Getting the new code"
  git pull --ff-only

  echo "==> Building (the site keeps running meanwhile)"
  "${compose[@]}" build

  echo "==> New website live"
  "${compose[@]}" up -d --no-deps frontend

  if [[ $now == 0 ]] && "${compose[@]}" ps --status running --services 2>/dev/null | grep -qx backend; then
    pause
    # If this script is stopped (Ctrl+C) or fails, don't leave jobs paused
    trap resume EXIT
    echo "==> New jobs paused. Waiting for running jobs to finish (at most $(( max_wait / 60 )) minutes)"
    local waited=0 n
    while :; do
      n=$(busy) || { echo "    Couldn't ask the backend how busy it is; going ahead."; break; }
      [[ "$n" == "0" ]] && { echo "    No jobs running."; break; }
      if (( waited >= max_wait )); then
        echo "!!  Still $n job(s) going after $(( max_wait / 60 )) minutes. Jobs are allowed again and"
        echo "    the old backend keeps running. Run this again later, or with --now."
        exit 1
      fi
      echo "    $n job(s) still going ($(( waited / 60 )) min so far)…"
      sleep 15
      waited=$(( waited + 15 ))
    done
  fi

  echo "==> Swapping in the new backend and anything else that changed"
  "${compose[@]}" up -d
  # The new backend starts with no pause file left over from the wait
  trap - EXIT
  resume
  echo "==> Done. The site is up to date."
}

main "$@"
