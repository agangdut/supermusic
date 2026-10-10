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
    "artifacts": { "midi": "/app/data/artifacts/c323309a-…_sample.mid" },
    "metrics": { "duration_s": 70.8, "model": "basic" }
  },
  "error_detail": null
}
```

`status` is one of `queued`, `running`, `done` or `error`. Each artifact path ends in a file name you can download from `/artifacts/{file name}`.

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
| `POST` | `/midi/convert` | `source_path`*, `onset_sensitivity` (0.6), `model` ("basic") |
| `GET` | `/midi/jobs/{id}` | |
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

Paths like `source_path` are **server** paths, the ones `/upload/*` returns.

## Music Map

| Method | Path | JSON body (* = one of) | Returns |
|---|---|---|---|
| `POST` | `/map/build` | `csv_path`* or `sample: true`*, `neighbors` (4), `clusters` (auto), `weights` | the whole map, right away (no job) |

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
