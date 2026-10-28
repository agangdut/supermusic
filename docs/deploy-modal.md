# Transcription on Modal's GPUs

On a server's CPU, a Full band transcription takes minutes per song, and renting a GPU server around the clock is expensive. [Modal](https://modal.com) rents GPUs by the second instead: SuperMusic's transcription engines (YourMT3+, MuScriptor and GAME, the Lead vocal model) run there on a GPU that starts when someone needs it and stops a couple of minutes later. Your own server keeps running the site, with your domain, set up as in [Running SuperMusic as a public website](deploy.md).

Everything Modal runs is described in one file, [`deploy/modal_app.py`](../deploy/modal_app.py). The engines can only be reached with your Modal keys, not from the internet.

## What you need

- The site running on your server ([deploy.md](deploy.md)). You can skip `--profile engines` there: Modal replaces it.
- A Modal account ([modal.com](https://modal.com), sign in with GitHub). The free Starter plan includes $30 of compute a month.
- Python 3.10 or newer on your computer, and this repository cloned.
- For MuScriptor (the most accurate Full band mode): a [Hugging Face](https://huggingface.co) read token, after accepting the licence on [MuScriptor/muscriptor-medium](https://huggingface.co/MuScriptor/muscriptor-medium).

## 1. Put the engines on Modal

On your computer:

```bash
pip install modal
modal setup                                   # opens your browser to sign in
modal secret create supermusic HF_TOKEN=hf_... # leave out HF_TOKEN=... if you don't use MuScriptor
modal deploy deploy/modal_app.py
```

The first deploy builds the engines' images, which takes 10 to 20 minutes; later deploys take a minute unless their dependencies change. Nothing runs (or costs anything) until a job asks for it.

## 2. Connect your server to them

In the Modal dashboard, go to **Settings → API Tokens** and create a token for the server (if your workspace makes tokens expire, note the date and make a new one before then). Add it and the engines to use to the server's `.env`:

```bash
SM_MODAL_ENGINES=yourmt3,muscriptor,game
MODAL_TOKEN_ID=ak-...
MODAL_TOKEN_SECRET=as-...
```

Leave `muscriptor` out of the list if the Modal secret has no `HF_TOKEN`. Then restart the backend:

```bash
docker compose -f docker-compose.prod.yml up -d --build backend
```

Run a Full band transcription in the Studio to check it: the job card says "starting a GPU" and then counts sections. The first time each engine runs, its model downloads into Modal's `supermusic-models` volume (a few hundred MB to a few GB), so that job takes a few minutes longer.

When you pull new code that changes `services/` or `deploy/modal_app.py`, run `modal deploy deploy/modal_app.py` again.

## What it costs

From [modal.com/pricing](https://modal.com/pricing), October 2026. GPUs are NVIDIA T4s, the cheapest Modal offers, at $0.59 an hour, billed by the second.

- A Full band transcription takes about as long as the song, plus up to a minute to start the GPU if none is running: around **$0.03 to $0.05 for a 3-minute song**.
- A GPU stays on for two minutes after its last job, so songs in a row don't each pay the start-up.
- Nothing is charged while no one transcribes. The $30 of monthly free credit covers several hundred songs.

For faster jobs, deploy with `SM_MODAL_GPU=L4 modal deploy deploy/modal_app.py` (about 1.5 times faster, about 1.35 times the price per second). Set a spending limit in the Modal dashboard under **Settings → Usage and limits**.

MuScriptor and GAME are licensed for **non-commercial use only**. On a site that makes money, use `SM_MODAL_ENGINES=yourmt3`.

Stem separation, General, Piano and Piano cover still run on your server's CPU.

## Music Map sound search

CLAP, which gives songs a "sound" description for the Music Map, is light enough for the server's CPU and runs there by default. To move it to Modal too, add `clap` to `SM_MODAL_ENGINES`.

## Hosting the whole site on Modal

Modal can also run the site itself, so there is no server at all. The catch: the address is `https://<workspace>--supermusic.modal.run`, and using your own domain there needs Modal's Team plan ($250 a month). The always-on site container costs about $45 a month on top of the GPUs.

To do it, put the site's settings in the secret and deploy with `SM_MODAL_SITE=1`:

```bash
modal secret create supermusic --force \
  SITE_DOMAIN=<workspace>--supermusic.modal.run \
  JWT_SECRET_KEY=$(openssl rand -hex 32) \
  CONTACT_EMAIL=you@example.com \
  HF_TOKEN=hf_... LASTFM_API_KEY=...
SM_MODAL_SITE=1 CONTACT_EMAIL=you@example.com modal deploy deploy/modal_app.py
```

Your workspace name is shown at the top left of the Modal dashboard. Any setting from [`deploy/production.env.example`](../deploy/production.env.example) can go in the secret. Accounts, uploads and results are kept on the `supermusic-data` volume; back them up with `modal volume get supermusic-data supermusic.db ./backup/`.

Things to know about this setup:

- Modal cuts off any request after 150 seconds. Jobs aren't affected (they run in the background), but building a map from an extremely large library could come close.
- Only one site container ever runs, because the job line lives in its memory and only one container may write the database. A deploy briefly overlaps the old and new container, so deploy at a quiet time.
