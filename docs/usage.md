# Usage guide

On a public SuperMusic site, open it in your browser and sign in (top right) to run stems and MIDI jobs. Running it yourself, start it with `docker compose up --build` and open http://localhost:3000. The Studio, where you upload songs, is at `/upload`.

## In the browser

![Upload page](img/upload.png)

### Turn a song into MIDI

1. Under **Audio**, choose an `.mp3`, `.wav` or `.flac` file.
2. Pick a **MIDI model**:
   - **Auto** (the default) listens to the song and picks one of the modes below. The finished job says what it detected and what it chose.
   - **Full band** uses MuScriptor, the most accurate mode on pop and band mixes. It writes a track per instrument (vocals, piano, guitar, bass, strings, drums and more). It runs in its own container, uses your NVIDIA GPU if you have one, and needs a Hugging Face token (see [configuration](configuration.md)). Expect roughly 0.8 seconds per second of music on a 6 GB gaming GPU (an RTX 2060), and several times longer on a CPU; the job card shows "section X of Y" and the time left.
   - **Full band (YourMT3+)** is the older full-band model: about 3x faster, less accurate on pop.
   - **Stems** splits the song into parts and gives you one MIDI file with a track per instrument: piano, bass, guitar, vocals, other, and drums. You can pick which stems to transcribe. Useful when neither full-band service is running.
   - **Piano** is for solo piano. It was trained on MAESTRO and also captures how hard each note is played and the sustain pedal.
   - **General** is the fastest, and fine for a single non-piano instrument.
   - **Piano cover** arranges the song for piano (Pop2Piano) instead of transcribing it note for note.

   Leave **Voice as its own melody** on to get the singer as a clean "Lead vocal" track instead of stray notes on other instruments. See [Voices](transcription-accuracy.md#voices). Tick **Playable by two hands** for a left/right hand part a pianist can play ([how](playable-piano.md)).

   The first run of each model downloads its weights into `data/models`.
3. Click **Transcribe → MIDI**.
4. The job appears under **Jobs** with live progress. If others are ahead of you, it says how many jobs are waiting first. When it finishes, play the piano preview, check the melody match score (if the voice was separated), and download the `.mid` file.

### Split a song into stems

1. Choose an audio file under **Audio**.
2. Click **Separate Stems**.
3. You get four `.wav` files: vocals, drums, bass and other.

Demucs is heavy, so this can take a few minutes on a CPU.

### Enrich a CSV of tracks

1. Under **CSV**, choose a `.csv` file.
2. Click **Enrich CSV** and download the enriched copy when it's done.

Each row needs either a `youtube_url` or a `local_path` that points to an audio file **the server can see** (for Docker, a path inside `./data`, written as `/app/data/...`). Rows without reachable audio are kept but not enriched. Columns like `title` and `artist` are used for MusicBrainz lookups.

```csv
title,artist,youtube_url,local_path
Me at the zoo,jawed,https://www.youtube.com/watch?v=jNQXAC9IVRw,
My demo,Me,,/app/data/raw/uploads/audio/demo.mp3
```

### Explore the Music Map

The Music Map is the home page. It starts with a sample library; click **Import Spotify / Apple Music** to use your own CSV or listening history, or **From Last.fm** to import your scrobbles by username (the server needs a `LASTFM_API_KEY`). The [Music Map guide](music-map.md) explains what you're looking at.

## From the command line

Every feature is also an API call. Uploading a file gives you a server path, and you pass that path to a job. Jobs only accept paths the server gave you.

```bash
# 1. Upload
curl -F "file=@song.mp3" http://localhost:8000/upload/audio
# → {"success": true, "path": "/app/data/raw/uploads/audio/9aQ.../song.mp3", ...}

# 2. Start a job
curl -X POST http://localhost:8000/midi/convert \
     -H "Content-Type: application/json" \
     -d '{"source_path": "/app/data/raw/uploads/audio/9aQ.../song.mp3"}'
# → {"id": "c323309a-…", "status": "queued", ...}

# 3. Check on it until status is "done"
curl http://localhost:8000/midi/jobs/c323309a-…
# → {"status": "done", "result": {"artifacts": {"midi": "/app/data/artifacts/Xk3v.../song (Auto).mid"}}}

# 4. Download the result (the folder and file name after /artifacts/)
curl -o "song (Auto).mid" "http://localhost:8000/artifacts/Xk3v.../song%20(Auto).mid"
```

Download straight from a YouTube, SoundCloud or Bandcamp link (API only, and turned off on public sites):

```bash
curl -X POST http://localhost:8000/tracks/download \
     -H "Content-Type: application/json" \
     -d '{"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"}'
```

All endpoints are listed in the [API reference](api.md), and you can try them at **http://localhost:8000/docs**.

## Run the tests

```bash
docker compose exec backend python -m pytest -q backend/tests
```

## Common problems

| You see | Try |
|---|---|
| Backend keeps restarting | `docker compose logs backend` shows the error. |
| A job says `error` | The job card shows what went wrong and what to try. Through the API, read `error_detail` and `error_hint` on `/{area}/jobs/{id}`. |
| A job says it was stopped by a server restart | The server restarted while it ran. Click **Try again**. Finished jobs are kept. |
| "Sign in to run this" | The site only runs stems and MIDI jobs for signed-in people. Sign in (it's free) and try again. |
| "You already have 3 jobs going" or "20 jobs in the last hour" | Each person has a limit so the line stays fair. Wait for a job to finish, or try later. |
| "Songs can be up to 15 minutes long" | Trim the file, or split a long mix into songs first. |
| Full band says the model couldn't load | `HF_TOKEN` is missing or empty in `.env`, or the licence on [muscriptor-medium](https://huggingface.co/MuScriptor/muscriptor-medium) isn't accepted. Fix it, then `docker compose up -d muscriptor`. Auto falls back to YourMT3+ meanwhile. |
| Download job fails on YouTube | YouTube changes often. Rebuild to get the newest yt-dlp: `docker compose build --no-cache backend`. |
