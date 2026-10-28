# Running SuperMusic on Modal

[Modal](https://modal.com) runs the whole site for you: no server to rent or keep updated. The website and API run in one small container that is always on, and the transcription models run on GPUs that start when someone needs them and stop a couple of minutes later, so you pay for GPU time by the second. Everything is described in one file, [`deploy/modal_app.py`](../deploy/modal_app.py).

If you'd rather run it on a server of your own, follow [Running SuperMusic as a public website](deploy.md) instead.

## What you need

- A Modal account ([modal.com](https://modal.com), sign in with GitHub). The free Starter plan includes $30 of compute a month.
- Python 3.10 or newer on your computer, and this repository cloned.
- Optional: a [Hugging Face](https://huggingface.co) read token if you want MuScriptor (Full band), and a free [Last.fm API key](https://www.last.fm/api/account/create) for Last.fm import and better genres.

## 1. Sign in to Modal

```bash
pip install modal
modal setup
```

`modal setup` opens your browser to connect this computer to your Modal account.

## 2. Store the settings

The site's settings and passwords live in a Modal *secret* called `supermusic`. Your site's address will be `https://<your workspace>--supermusic.modal.run`, where the workspace name is shown at the top left of the Modal dashboard (usually your GitHub username).

```bash
modal secret create supermusic \
  SITE_DOMAIN=<workspace>--supermusic.modal.run \
  JWT_SECRET_KEY=$(openssl rand -hex 32) \
  CONTACT_EMAIL=you@example.com \
  HF_TOKEN=hf_... \
  LASTFM_API_KEY=...
```

`SITE_DOMAIN`, `JWT_SECRET_KEY` and `CONTACT_EMAIL` are required; leave out the others if you don't have them. Any setting from [`deploy/production.env.example`](../deploy/production.env.example) can go in the secret too (`SM_ADMINS`, the `SMTP_` settings for password-reset email, `SM_JOBS_PER_HOUR` and so on). To change the secret later, edit it in the Modal dashboard under **Secrets**, then deploy again.

## 3. Deploy

```bash
CONTACT_EMAIL=you@example.com modal deploy deploy/modal_app.py
```

`CONTACT_EMAIL` (and `SPOTIFY_CLIENT_ID`, if you use the Save to Spotify button) has to be on this command line too, because it is built into the website's pages. The first deploy builds the images, which takes 15 to 25 minutes; later deploys reuse them and take a minute or two unless the dependencies change. When it finishes, Modal prints the site's address. Open it, create your account, and add your username to `SM_ADMINS` in the secret if you want the admin page.

The first time someone runs each transcription mode, its model downloads into the `supermusic-models` volume (a few hundred MB to a few GB), so that first job takes a few minutes longer.

To update the site after pulling new code, run the same `modal deploy` command. Jobs that are running at that moment stop and show a **Try again** button, as on a server.

## What runs where

| Part | Where | Runs |
|---|---|---|
| Website, API, accounts, Music Map, stems, Basic Pitch, Piano, Piano cover | `web`: one CPU container, always on | 1 core and 2 GB reserved, up to 8 cores and 16 GB during jobs |
| Full band (YourMT3+) | `YourMT3`: GPU | only during jobs |
| Full band (MuScriptor) | `MuScriptor`: GPU | only during jobs, needs `HF_TOKEN` |
| Lead vocal, and the voice/rest split for it | `Game`: GPU | only during jobs |
| Music Map sound search | `Clap`: small CPU container | only during imports and searches |

Accounts, uploads and results are kept on the `supermusic-data` volume, and model weights on `supermusic-models`. The engines can only be reached by the site, not from the internet.

The GPUs are NVIDIA T4s, the cheapest Modal offers. For faster jobs, deploy with `SM_MODAL_GPU=L4` (about 1.5 times faster, about 1.35 times the price per second).

## What it costs

Prices from [modal.com/pricing](https://modal.com/pricing) in October 2026:

- **The site container**, always on with 1 core and 2 GB reserved: about $45 a month. On the Starter plan the $30 of free credit covers most of that.
- **Jobs on the site container** (stems, Piano and the rest) add roughly $0.01 to $0.03 per song.
- **A Full band transcription** on a T4 ($0.59 an hour) takes about as long as the song plus a minute to start the GPU: around $0.03 to $0.05 for a 3-minute song.

Set a spending limit in the Modal dashboard under **Settings → Usage and limits** so a busy day can't surprise you.

MuScriptor and GAME (Lead vocal) are licensed for **non-commercial use only**. If the site makes money, add `SM_MODAL_ENGINES=yourmt3,clap` to the secret so they are never used.

## Backups

Download the accounts database and shared maps now and then:

```bash
modal volume get supermusic-data supermusic.db ./backup/
modal volume get supermusic-data shared_maps ./backup/
```

## Things to know

- **Your own domain** (supermusic.com rather than a modal.run address) needs Modal's Team plan. Until then, the modal.run address works and has HTTPS.
- **Requests are cut off after 150 seconds** by Modal. Jobs aren't affected (they run in the background and the page checks on them), but building a Music Map from an extremely large library on one core could come close.
- **Only one site container ever runs**, because the job line lives in its memory and only one container may write the database. A deploy briefly overlaps the old and new container, so deploy at a quiet time.
- **Logs** are in the Modal dashboard under **Apps → supermusic**, one tab per container.
