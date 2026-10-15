// frontend/lib/api.js
// Thin wrapper around your FastAPI endpoints + a few helpers.
// Requires "@/utils/fetcher" (API_BASE, apiFetch) and (optionally) NEXT_PUBLIC_ARTIFACT_BASE.
//
// Env (frontend):
//   NEXT_PUBLIC_API_BASE         -> e.g. http://localhost:8000
//   NEXT_PUBLIC_ARTIFACT_BASE    -> e.g. http://localhost:8000/artifacts
//
import { API_BASE, apiFetch } from "@/utils/fetcher";

const ARTIFACT_BASE =
  process.env.NEXT_PUBLIC_ARTIFACT_BASE || `${API_BASE}/artifacts`;

// --- Helpers ---------------------------------------------------------------

/** Map backend job_type -> router area used for polling. */
export function areaForJobType(job_type) {
  switch (job_type) {
    case "midi_conversion": return "midi";
    case "csv_enrichment":  return "csv";
    case "stem_separation": return "stems";
    case "track_download":  return "tracks";
    default: return null;
  }
}

/** If artifacts are file paths (e.g., /tmp/supermusic/artifacts/uuid_file.ext),
 *  rewrite them to URLs served by your static mount (/artifacts). */
export function normalizeJobArtifacts(job) {
  if (!job?.result?.artifacts) return job;
  const out = { ...job, result: { ...job.result, artifacts: {} } };
  for (const [k, v] of Object.entries(job.result.artifacts)) {
    out.result.artifacts[k] = toArtifactUrl(v);
  }
  return out;
}

export function toArtifactUrl(pathOrUrl) {
  if (!pathOrUrl) return pathOrUrl;
  // Already a URL? leave it.
  if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl;
  // Strip any local prefix and use the filename.
  const file = String(pathOrUrl).split(/[\\/]/).pop();
  return `${ARTIFACT_BASE}/${encodeURIComponent(file)}`;
}

async function postJSON(path, body) {
  return apiFetch(path, {
    method: "POST",
    body: JSON.stringify(body ?? {}),
  });
}

// --- Job creation endpoints -----------------------------------------------

/** POST /midi/convert */
/** stems: which stems to transcribe in Stems mode. stem_job_id: reuse an earlier separation (no source_path needed). */
export async function midiConvert({ source_path, onset_sensitivity = 0.6, model = "basic", playable = false, hand_span = 14, vocal_track = true, stems, stem_job_id }) {
  const job = await postJSON("/midi/convert", { source_path, onset_sensitivity, model, playable, hand_span, vocal_track, stems, stem_job_id });
  return normalizeJobArtifacts(job);
}

/** POST /csv/enrich-files — several CSV / Spotify / Apple Music files merged into one enriched CSV. */
export async function enrichFiles(files, { lookup = true, limit } = {}) {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  form.append("lookup", lookup ? "true" : "false");
  if (limit) form.append("limit", String(limit));
  return apiFetch("/csv/enrich-files", { method: "POST", body: form });
}

/** POST /csv/enrich */
export async function csvEnrich({ csv_path, strategy = "youtube+acousticbrainz", options = {} }) {
  const job = await postJSON("/csv/enrich", { csv_path, strategy, options });
  return normalizeJobArtifacts(job);
}

/** POST /stems/separate */
export async function stemsSeparate({ audio_path, model = "htdemucs", stems = ["vocals","drums","bass","other"] }) {
  const job = await postJSON("/stems/separate", { audio_path, model, stems });
  return normalizeJobArtifacts(job);
}

/** POST /tracks/download */
export async function trackDownload({ url, format = "bestaudio", title_hint }) {
  const job = await postJSON("/tracks/download", { url, format, title_hint });
  return normalizeJobArtifacts(job);
}

// --- Job polling -----------------------------------------------------------

/** GET /{area}/jobs/{id} */
export async function getJob(area, id) {
  const job = await apiFetch(`/${area}/jobs/${id}`);
  return normalizeJobArtifacts(job);
}

/** Poll a job until it reaches a terminal state.
 *  opts: { intervalMs=800, timeoutMs=180000, onUpdate?: (job)=>void }
 */
export async function pollJob(jobOrId, opts = {}) {
  const { intervalMs = 800, timeoutMs = 180000, onUpdate } = opts;
  let id, area;

  if (typeof jobOrId === "string") {
    id = jobOrId;
  } else if (jobOrId?.id) {
    id = jobOrId.id;
    area = areaForJobType(jobOrId.job_type);
  }
  if (!area) area = jobOrId?.area || areaForJobType(jobOrId?.job_type);
  if (!id || !area) throw new Error("pollJob requires a job object (with job_type) or {area,id}");

  const terminal = new Set(["success", "failed", "canceled", "done", "error"]);
  const start = Date.now();

  // simple jittered polling
  let delay = intervalMs;
  while (true) {
    const job = await getJob(area, id);
    onUpdate?.(job);
    if (terminal.has(job.status)) return job;

    if (Date.now() - start > timeoutMs) {
      const e = new Error("Polling timed out");
      e.job = job;
      throw e;
    }
    await new Promise((r) => setTimeout(r, delay));
    // gentle backoff up to ~2s
    delay = Math.min(2000, Math.round(delay * 1.2));
  }
}

// --- Optional convenience: run + poll in one call -------------------------

export async function runAndWait(makeJobFn, { onUpdate, ...pollOpts } = {}) {
  const job = await makeJobFn();
  const area = areaForJobType(job.job_type);
  return pollJob({ ...job, area }, { onUpdate, ...pollOpts });
}

// --- Notes -----------------------------------------------------------------
// • Make sure your backend serves artifacts publicly. In FastAPI:
//
//   from fastapi.staticfiles import StaticFiles
//   import os
//   ART_DIR = os.getenv("SUPERMUSIC_ARTIFACT_DIR", "/tmp/supermusic/artifacts")
//   app.mount("/artifacts", StaticFiles(directory=ART_DIR), name="artifacts")
//
// • Then set NEXT_PUBLIC_ARTIFACT_BASE=http://localhost:8000/artifacts
//   so normalizeJobArtifacts() can build browser-friendly URLs.
//
// • If/when you add real file uploads, plug your upload step in before
//   calling midiConvert/csvEnrich/stemsSeparate to obtain a server-side path.

// --- Music map ---------------------------------------------------------------

/** POST /map/build — returns { tracks, edges, clusters, hidden_connections, insights, recommendations, meta } */
export async function buildMap({ csv_path, sample = false, neighbors = 4, clusters = null, weights = {} }) {
  return postJSON("/map/build", { csv_path, sample, neighbors, clusters, weights });
}

/** "Songs you may like" for one track of the map (same library, same slider weights). */
export async function likeSongs({ csv_path, sample = false, id, weights = {}, limit = 8 }) {
  return postJSON("/map/like", { csv_path, sample, id, weights, limit });
}

/** Songs whose sound matches a typed description (needs sound data from an import with CLAP running). */
export async function searchSound({ csv_path, sample = false, query, limit = 20 }) {
  return postJSON("/map/search", { csv_path, sample, query, limit });
}

/** Upload a CSV and return its server path. */
export async function uploadCsv(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await apiFetch("/upload/csv", { method: "POST", body: form });
  if (!res?.path) throw new Error(res?.detail || "Upload failed");
  return res.path;
}

/** POST /map/import — Spotify / Apple Music exports (several files at once). Returns an import job. */
export async function importLibrary(files, { enrich = true, listen = true, listenLimit = null } = {}) {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  form.append("enrich", enrich ? "true" : "false");
  form.append("listen", listen ? "true" : "false");
  if (listenLimit) form.append("listen_limit", String(listenLimit));
  return apiFetch("/map/import", { method: "POST", body: form });
}

/** POST /map/import/{id}/skip-listen — stop listening to previews and draw the map now. */
export async function skipListening(id) {
  return apiFetch(`/map/import/${id}/skip-listen`, { method: "POST" });
}

/** GET /map/import/{id} */
export async function getImport(id) {
  return apiFetch(`/map/import/${id}`);
}

/** GET /map/estimate — seconds the server expects drawing a map of `tracks` songs to take. */
export async function getMapEstimate(tracks) {
  const res = await apiFetch(`/map/estimate?tracks=${encodeURIComponent(tracks)}`);
  return res?.seconds ?? null;
}
