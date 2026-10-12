# 🔌 API reference

Base URL: `http://localhost:8000` · Live, clickable docs: **[/docs](http://localhost:8000/docs)**

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
    "artifacts": { "midi": "/app/data/artifacts/sample (General).mid" },
    "metrics": { "duration_s": 70.8, "model": "basic" }
  },
  "error_detail": null
}
```

`status` is one of `queued`, `running`, `done` or `error`. Each artifact path ends in a file name you can download from `/artifacts/{file name}` (URL-encode the spaces). Files are named after the song and what they are, e.g. `Artist - Song (Full band).mid`, `Artist - Song (Full band, two hands).mid`, `Artist - Song (vocals).wav`. Words like "(Official Music Video)" are dropped from the upload's name, and a second run of the same song gets `(2)` on the end.

> ⚠️ Jobs are kept in memory, so restarting the backend forgets them. The files stay in `data/artifacts`.

## Files

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/upload/audio` | form field `file` (mp3, wav, flac, m4a, ogg, opus) | `{ success, path, filename, size }` |
| `POST` | `/upload/csv` | form field `file` (csv) | same as above |
| `GET` | `/artifacts/{name}` | | the file |

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

> Accounts work, but no other endpoint requires sign-in yet, and accounts are lost on restart. See the [roadmap](roadmap.md).

## Live updates

`ws://localhost:8000/ws/jobs` is a WebSocket that pushes job updates as they happen. The UI currently polls instead.

## Health

| Method | Path | Returns |
|---|---|---|
| `GET` | `/healthz` | `{ "ok": true, "status": "healthy" }` |
| `GET` | `/` | welcome message with links |

**Tested end to end:** upload, MIDI, stems, CSV, download, accounts, Music Map. **Not yet tested end to end:** UMAP, batch, export, WebSocket.
