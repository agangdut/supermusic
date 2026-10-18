# Running SuperMusic as a public website

This guide puts SuperMusic on one Linux server with its own domain and HTTPS. It takes about an hour the first time.

## What you need

- **A server.** 8 CPU cores and 16 GB of memory is a comfortable start (for example a Hetzner CCX33 or CPX51, or a similar VPS from DigitalOcean, OVH or Linode). The Music Map, CSV enrichment and accounts are light. Stem separation and transcription each keep a few cores busy for a few minutes per song, so they run one at a time and everyone else waits in line (see [Capacity](#capacity)).
- **A domain name** (any registrar) with an `A` record pointing at the server's IP address.
- **Docker** on the server: `curl -fsSL https://get.docker.com | sh`.

## 1. Get the code and settings onto the server

```bash
git clone https://github.com/agangdut/supermusic.git /srv/supermusic
cd /srv/supermusic
cp deploy/production.env.example .env
nano .env
```

In `.env`, set at least:

| Setting | Value |
|---|---|
| `SITE_DOMAIN` | your domain, e.g. `supermusic.example.com` |
| `JWT_SECRET_KEY` | the output of `openssl rand -hex 32` |
| `CONTACT_EMAIL` | where people write about privacy, copyright or a lost password |

Two more are worth setting soon after the first start:

- `SM_ADMINS`: your username on the site. Sign up first, then add it and restart the backend. `/admin` then shows visitor stats and anything people reported, with buttons to take it down.
- `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`: an email service so people who forget their password get a reset link. Resend's free plan is enough: verify your domain there (it shows the DNS records to add), then use `smtp.resend.com`, user `resend` and your API key as the password. Until this is set, the "Forgot your password?" page asks people to write to `CONTACT_EMAIL`.

The other settings are explained in the file. The defaults are safe for a launch: only signed-in people can run heavy jobs, one heavy job runs at a time, uploads are deleted after 7 days, and downloading from YouTube links is off.

## 2. Open the firewall

Only ports 22 (SSH), 80 and 443 should be reachable. With `ufw`:

```bash
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable
```

Docker publishes only Caddy's ports in the production setup; the backend, website and model servers are reachable only from inside Docker.

## 3. Start it

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The first build downloads the machine-learning libraries and takes 10 to 20 minutes. When it's done, open `https://<your domain>`. Caddy gets the HTTPS certificate by itself the first time someone visits, which needs the domain's DNS to already point at the server.

To also run the extra transcription engines (Full band with YourMT3+ and MuScriptor, and the Lead vocal model), add the `engines` profile. Each needs about 3 to 4 GB of memory:

```bash
docker compose -f docker-compose.prod.yml --profile engines up -d --build
```

MuScriptor's weights are gated: accept the licence on [huggingface.co/MuScriptor/muscriptor-medium](https://huggingface.co/MuScriptor/muscriptor-medium) and put a read token in `HF_TOKEN`. MuScriptor and the Lead vocal model are licensed for **non-commercial use only**, so leave them off if the site makes money.

## 4. Back it up

Accounts, votes and shared maps live in `data/`. Back them up every day and copy the backup to another machine or to object storage:

```bash
crontab -e
# add:
0 4 * * * cd /srv/supermusic && ./deploy/backup.sh && find data/backups -mtime +14 -delete
```

To restore, stop the site, put `supermusic.db` back in `data/` and unpack `shared_maps` and `processed/library` into `data/`, then start it again.

## 5. Watch it

- An uptime check (UptimeRobot, Better Stack and others have free plans) on `https://<your domain>/api/healthz` tells you when the site is down.
- The admin page (`/admin`, for the usernames in `SM_ADMINS`) shows visitors per day, the most viewed pages, where visitors came from, and reports waiting for you.
- `docker compose -f docker-compose.prod.yml logs -f backend` shows what the backend is doing.
- `df -h` and `docker system df` show disk use. Old uploads and results are deleted after `SM_KEEP_DAYS` days.

## Updating

```bash
cd /srv/supermusic
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Jobs that are running during an update stop, and show as "stopped by a server restart" with a button to start them again. Finished results are kept.

## Capacity

Light requests (the map, sign-in, shared maps, the atlas) take well under a second and a server like the one above handles hundreds of people browsing at once.

Heavy jobs are the limit. On 4 CPU cores, separating a 3-minute song takes about 3 to 4 minutes and the full-band transcription about 5. With `SM_HEAVY_WORKERS=1`, jobs run one after another, so a person who is fifth in line waits around 15 to 20 minutes. Ways to shorten the wait:

- Raise `SM_HEAVY_WORKERS` on a bigger server (allow about 4 cores and 6 GB of memory per worker).
- Put the model servers on a GPU. On an NVIDIA GPU a song takes seconds instead of minutes. Add `docker-compose.gpu.yml` the same way as for local use.

Each person can have `SM_MAX_ACTIVE_JOBS` jobs waiting or running and start `SM_JOBS_PER_HOUR` per hour, so one person can't fill the line.

## What the production setup changes

Compared with `docker compose up` for local use:

- Caddy serves the site over HTTPS and sends `/api/*` to the backend, so the site and API share one address.
- The API's interactive docs (`/docs`) are off, and the backend refuses to start without a real `JWT_SECRET_KEY` and `CORS_ORIGINS`.
- The API only opens files it saved itself (uploads and results), and results are stored under random folder names so download links can't be guessed.
- Uploads are capped at `SM_MAX_UPLOAD_MB` and songs at `SM_MAX_SONG_MINUTES`.
- Sign-ups, sign-ins, uploads and imports are rate-limited per address.
