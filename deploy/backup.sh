#!/usr/bin/env bash
# Back up everything that can't be re-made: accounts and votes (the SQLite file),
# shared maps, and the libraries behind people's own maps.
#
#   ./deploy/backup.sh          # writes data/backups/supermusic-<date>.tar.gz
#
# Run it daily from cron, and copy the file off this server (another machine, or
# object storage such as Backblaze B2 or Cloudflare R2): a backup on the same
# disk doesn't help if the server is lost.
#   0 4 * * *  cd /srv/supermusic && ./deploy/backup.sh && find data/backups -mtime +14 -delete
set -euo pipefail
cd "$(dirname "$0")/.."
stamp=$(date +%Y-%m-%d_%H%M)

# Runs inside the backend container, so it works while the site is up and
# doesn't need write access to data/ from this shell
docker compose -f docker-compose.prod.yml exec -T backend python - "$stamp" <<'PY'
import os, sqlite3, sys, tarfile, tempfile
stamp = sys.argv[1]
data = "/app/data"
out_dir = os.path.join(data, "backups")
os.makedirs(out_dir, exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    db = os.path.join(tmp, "supermusic.db")
    src, dst = sqlite3.connect(os.path.join(data, "supermusic.db")), sqlite3.connect(db)
    src.backup(dst)  # a consistent copy even while people are using the site
    dst.close()
    out = os.path.join(out_dir, f"supermusic-{stamp}.tar.gz")
    with tarfile.open(out, "w:gz") as tar:
        tar.add(db, "supermusic.db")
        for sub in ("shared_maps", "processed/library"):
            if os.path.isdir(os.path.join(data, sub)):
                tar.add(os.path.join(data, sub), sub)
print(f"data/backups/supermusic-{stamp}.tar.gz")
PY
