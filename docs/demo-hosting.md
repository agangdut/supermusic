# Free demo hosting: GitHub Pages + Hugging Face Spaces

A quick way to show SuperMusic without renting a server. For real users, follow
[Running SuperMusic as a public website](deploy.md) instead.

- **Website:** https://agangdut.github.io/supermusic/, a static export of the frontend built by
  `.github/workflows/pages.yml` on every push to `master`.
- **API:** a Hugging Face Space (Docker, free CPU tier) built by `.github/workflows/hf-space.yml`
  from `deploy/hf-space/` whenever the backend changes. It is created the first time it runs.

## One-time setup

1. In the repository's **Settings → Pages**, set **Source** to **GitHub Actions**.
2. On Hugging Face, create a token with **Write** access (Settings → Access Tokens).
3. In the repository's **Settings → Secrets and variables → Actions**, add it as `HF_TOKEN`.
4. Run the **Hugging Face Space** workflow from the Actions tab. It creates
   `<your HF username>/supermusic`, then rebuilds the website pointing at it. The Space's first
   build takes 10 to 20 minutes because of the machine-learning libraries.

## What works and what doesn't

- Works: Music Map, imports, CSV clean-up, accounts, sharing, audio to MIDI and stems (slowly, on
  2 CPU cores).
- Not included: the separate model servers (YourMT3+, MuScriptor, the vocal model and CLAP), so
  Full band transcription, Lead vocal and describe-a-vibe search fall back or are off.
- Shared-map preview links (`/s/<id>`) render on a server, so the static site leaves them out.
- A free Space sleeps after 48 hours without visits and forgets its data when it restarts. While
  it is asleep the website still shows the sample Music Map.
