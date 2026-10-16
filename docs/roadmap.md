# Roadmap

What's planned, roughly in order. Ideas and pull requests are welcome; open an issue to talk one through first.

## The website

- Email: password reset, and the weekly digest by email
- Screens for what the API can already do: paste a link to download, batch processing, "download all" as a zip
- Live job progress pushed to the page instead of checked every two seconds
- Play stems in the browser (MIDI already has a piano preview)
- A separate worker process for heavy jobs, so they can run on another machine with a GPU
- Frontend tests, and lint checks in CI

## Music Map

- Recommend songs from outside your library (Last.fm or MusicBrainz "similar tracks", placed on your map)
- Import listening history straight from Last.fm
- Save snapshots of your map and watch your taste change over time
- A "Vibes" colour lens and a filter by vibe tag
- Suggest a link: listeners say "these two go together", and agreed pairs join the hidden links
- Trust scores: listeners whose fixes others keep agreeing with count for more
- A 30-second preview when you click a star

## Transcription

- Test MuScriptor on solo piano and classical music; if it matches the Piano model, Auto can get simpler
- Try MuScriptor with beam search and per-stem transcription
- A second piano-cover engine (AMT-APC) next to Pop2Piano
- Fine-tune on piano-cover pairs built with `scripts/build_cover_dataset.py` (see [training data](training-data.md))

## From the first prototype

`legacy/` holds the 2025 prototype. Parts not yet in the app:

- Split hour-long DJ mixes into tracks, with a CSV or CUE export
- Write tags (genre, BPM, key) back into your audio files
