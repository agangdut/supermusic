# Free demo hosting: GitHub Pages + Hugging Face Spaces

The live site is [www.supermusic.dev](https://www.supermusic.dev). This page is for a quick way to show your own copy without renting a server. For real users, follow
[Running SuperMusic as a public website](deploy.md) instead.

- **Website:** https://agangdut.github.io/supermusic/, a static export of the frontend built by
  `.github/workflows/pages.yml` on every push to `master`.
- **API (optional, currently not running):** a Hugging Face Space (Docker) built by
  `.github/workflows/hf-space.yml` from `deploy/hf-space/`. Docker Spaces need a Hugging Face PRO
  subscription. Without a server the site shows only the sample Music Map.

## One-time setup

1. In the repository's **Settings → Pages**, set **Source** to **GitHub Actions**.
That is all the static demo needs. To add the API later:

2. Subscribe to Hugging Face PRO and create a token with **Write** access (Settings → Access Tokens).
3. In the repository's **Settings → Secrets and variables → Actions**, add it as the secret `HF_TOKEN`.
4. Run the **Hugging Face Space** workflow from the Actions tab. It creates
   `<your HF username>/supermusic`. The first build takes 10 to 20 minutes.
5. Add the repository variable `API_BASE` = `https://<your HF username>-supermusic.hf.space`
   and rerun the **Pages demo** workflow.

## What works with the API

- Works: Music Map, imports, CSV clean-up, accounts, sharing, audio to MIDI and stems (slowly, on
  2 CPU cores).
- Not included: the separate model servers (YourMT3+, MuScriptor, the vocal model and CLAP), so
  Full band transcription, Lead vocal and describe-a-vibe search fall back or are off.
- Shared-map preview links (`/s/<id>`) render on a server, so the static site leaves them out.
- A free Space sleeps after 48 hours without visits and forgets its data when it restarts. While
  it is asleep the website still shows the sample Music Map.
