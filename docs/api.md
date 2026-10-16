# API reference

Base URL: `http://localhost:8000` when you run it yourself, or `https://<your domain>/api` on a public site. Running locally, the interactive docs at [/docs](http://localhost:8000/docs) let you try every endpoint (they're turned off on a public site).

## How jobs work

Long tasks don't block the request. You **start** a job and get back a job object right away, then **poll** it until `status` is `done` or `error`.

```json
{
  "id": "c323309a-d409-4760-98b2-33003fe99492",
  "job_type": "midi_conversion",
  "status": "done",
  "message": "MIDI conversion complete",
  "progress": 80,
  "result": {
    "artifacts": { "midi": "/app/data/artifacts/Xk3v9QmP2aL7wR4t/sample (General).mid" },
    "metrics": { "duration_s": 70.8, "model": "basic" }
  },
  "error_detail": null
}
```

`status` is `queued` while the job waits in line (its `message` says how many jobs are ahead), then `running`, then `done` or `error`. Each result sits in a folder with a random name, so download it from `/artifacts/{folder}/{file name}` (URL-encode the spaces). Files are named after the song and what they are, e.g. `Artist - Song (Full band).mid`, `Artist - Song (Full band, two hands).mid`, `Artist - Song (vocals).wav`. Words like "(Official Music Video)" are dropped from the upload's name.

Jobs are saved, so a finished job can still be fetched after the server restarts. Uploads and results are deleted after `SM_KEEP_DAYS` days (7 by default).

**Limits.** Each person can have 3 heavy jobs (stems, MIDI, batch, downloads) waiting or running and start 20 per hour; past that the API answers `429`. A public site can also require sign-in for heavy jobs (`401`). Job endpoints only accept paths returned by `/upload/*` or by an earlier job, and answer `404` for anything else. See [configuration](configuration.md#limits-for-a-public-site).

## Files

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/upload/audio` | form field `file` (mp3, wav, flac, m4a, ogg, opus; up to 100 MB and 15 minutes) | `{ success, path, filename, size }` |
| `POST` | `/upload/csv` | form field `file` (csv) | same as above |
| `GET` | `/artifacts/{folder}/{name}` | | the file |

## Jobs

| Method | Path | JSON body (* = required) |
|---|---|---|
| `POST` | `/midi/convert` | `source_path`* (or `stem_job_id`), `model` (default "basic"; see below), `vocal_track` (true), `playable` (false), `hand_span` (14), `composer` ("composer1", Piano cover only), `stems` (Stems only), `onset_sensitivity` (0.6) |
| `GET` | `/midi/jobs/{id}` | |
| `POST` | `/midi/melody-match` | `midi_path`*, and `vocals_path` or `audio_path` (returns scores right away) |
| `POST` | `/midi/playability` | `midi_path`*, `hand_span` (14) (returns scores right away) |
| `POST` | `/stems/separate` | `audio_path`*, `model` ("htdemucs"), `stems` |
| `GET` | `/stems/jobs/{id}` | |
| `POST` | `/csv/enrich` | `csv_path`*, `strategy` ("youtube+acousticbrainz"), `options` |
| `GET` | `/csv/jobs/{id}` | |
| `POST` | `/tracks/download` | `url`*, `format` ("bestaudio"), `title_hint` |
| `GET` | `/tracks/jobs/{id}` | |
| `POST` | `/visualization/umap` | `audio_paths`*, `n_components` (3), `n_neighbors` (15), `min_dist` (0.1), `metadata` |
| `GET` | `/visualization/jobs/{id}` | |
| `POST` | `/batch/process` | `audio_files`*, `operations` (["transcribe"]) |
| `GET` | `/batch/jobs/{id}` | |

MIDI models (`model`):

| Value | UI name | What it is |
|---|---|---|
| `auto` | Auto | Detects the instruments and picks one of the others |
| `muscriptor` | Full band | MuScriptor, most accurate on pop; needs the muscriptor service and `HF_TOKEN` |
| `multi` | Full band (YourMT3+) | YourMT3+; needs the yourmt3 service |
| `stems` | Stems | Splits into 6 parts and returns one multi-track MIDI (Piano, Bass, Guitar, Vocals, Other, plus a drum track) |
| `piano` | Piano | Solo piano, with velocity and pedal |
| `basic` | General | Basic Pitch, the fastest |
| `cover` | Piano cover | Pop2Piano arranges the song for piano |

A finished MIDI job's `result.artifacts` holds `midi` and a `preview` MP3 (plus `midi_original` when `playable` is on). Auto and Stems add `detected`, `chosen_model`, `reason` and `tracks` to `result.metrics`; jobs that separated the voice add melody match scores. While a job runs, `stage` and `eta_s` describe its progress.

Paths like `source_path` are **server** paths, the ones `/upload/*` returns.

## Music Map

| Method | Path | JSON body (* = one of) | Returns |
|---|---|---|---|
| `POST` | `/map/build` | `csv_path`* or `sample: true`*, `neighbors` (4), `clusters` (auto), `weights` | the whole map, right away (no job) |
| `POST` | `/map/import` | form: `files` (one or more Spotify / Apple Music exports or CSVs), `enrich` (true), `limit` (1500) | an import job `{id, status, progress, message, detected}` |
| `GET` | `/map/import/{id}` | | the job; when `status` is `done`, `result` holds the map |

`weights` scales how much each aspect shapes the map, from 0 to 2: `key`, `tempo`, `genre`, `mood`, `artist`, `era`. The response holds `tracks` (with `x`, `y`, `z` and `cluster`), `edges`, `clusters` (with `label` and `signal`), `hidden_connections`, `insights`, `recommendations` and `meta`. Limited to 5,000 tracks. See the [Music Map guide](music-map.md).

## Export

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET` | `/export/job/{id}` | | a zip of that job's files |
| `POST` | `/export/jobs` | `job_ids`*, `format` ("zip") | a zip of several jobs |

## Accounts

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/auth/register` | `username`* (3–50), `password`* (8–72), `email` | `{ access_token, token_type }` |
| `POST` | `/auth/login` | `username`*, `password`* | `{ access_token, token_type }` |
| `GET` | `/auth/me` | header `Authorization: Bearer <token>` | your profile |

Send the token as `Authorization: Bearer <token>` to act as your account (profiles, follows, shared maps, and heavy jobs when the site requires sign-in).

## Live updates

`ws://localhost:8000/ws/jobs` is a WebSocket. Send `{"type": "subscribe", "job_id": "..."}` for a job you started and it answers with that job's state. The website polls instead.

## Health

| Method | Path | Returns |
|---|---|---|
| `GET` | `/healthz` | `{ "ok": true, "status": "healthy" }` |
| `GET` | `/` | welcome message with links |

