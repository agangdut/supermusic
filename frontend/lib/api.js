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
  if (/^https?:\/\//i.test(pathOrUrl) || String(pathOrUrl).startsWith(ARTIFACT_BASE)) return pathOrUrl;
  // Each result sits in its own random folder: keep "<folder>/<file>", drop the server's prefix
  const parts = String(pathOrUrl).split(/[\\/]/).filter(Boolean);
  const at = parts.lastIndexOf("artifacts");
  const rel = at >= 0 && at < parts.length - 1 ? parts.slice(at + 1) : parts.slice(-1);
  return `${ARTIFACT_BASE}/${rel.map(encodeURIComponent).join("/")}`;
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
export async function enrichFiles(files, { lookup = true, limit, output = "combined" } = {}) {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  form.append("lookup", lookup ? "true" : "false");
  form.append("output", output);
  if (limit) form.append("limit", String(limit));
  return apiFetch("/csv/enrich-files", { method: "POST", body: form });
}

/** POST /csv/import-lastfm: read a Last.fm library by username, then enrich it in the background. */
export async function importLastfm({ username, lookup = true, limit, max_tracks }) {
  return postJSON("/csv/import-lastfm", { username, lookup, limit: limit || undefined, max_tracks: max_tracks || undefined });
}

/** GET /csv/lastfm/status: { enabled } (false when the server has no LASTFM_API_KEY). */
export async function lastfmStatus() {
  return apiFetch("/csv/lastfm/status");
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
export async function buildMap({ csv_path, sample = false, share_id, neighbors = 4, clusters = null, weights = {} }) {
  return postJSON("/map/build", { csv_path, sample, share_id, neighbors, clusters, weights });
}

/** "Songs you may like" for one track of the map (same library, same slider weights). */
export async function likeSongs({ csv_path, sample = false, share_id, id, weights = {}, limit = 8 }) {
  return postJSON("/map/like", { csv_path, sample, share_id, id, weights, limit });
}

/** Songs whose sound matches a typed description (needs sound data from an import with CLAP running). */
export async function searchSound({ csv_path, sample = false, share_id, query, limit = 20 }) {
  return postJSON("/map/search", { csv_path, sample, share_id, query, limit });
}

/** Save a snapshot of a map under a short link. Returns { id, delete_token, ... }. */
export async function shareMap({ map, title, by, listed = false, include_listening = true, weights = {}, source = {} }) {
  return postJSON("/map/share", { map, title, by, listed, include_listening, weights, ...source });
}

/** A shared map: { id, title, by, created, songs, has_library, map }. */
export async function getSharedMap(id) {
  return apiFetch(`/map/shared/${encodeURIComponent(id)}`);
}

/** Maps people chose to list publicly, with picture, showcase stats and upvotes. sort: "top" | "new". */
export async function listSharedMaps(sort = "top") {
  return apiFetch(`/map/shared?sort=${sort}`);
}

/** Upvote a shared map (up=false takes it back). Returns { votes, voted }. */
export async function voteSharedMap(id, up = true) {
  return postJSON(`/map/shared/${encodeURIComponent(id)}/vote`, { up });
}

/** The picture saved when a map was shared. */
export const sharedMapPicture = (id) => `${API_BASE}/map/shared/${encodeURIComponent(id)}/picture.png`;

export async function unshareMap(id, delete_token) {
  return postJSON(`/map/shared/${encodeURIComponent(id)}/delete`, { delete_token });
}

/** A fresh 30-second Deezer preview for one song: { preview, deezer_url, cover }. */
export async function getPreview({ artist, title }) {
  const q = new URLSearchParams({ title, artist: artist || "" });
  return apiFetch(`/map/preview?${q}`);
}

/** One YouTube video id (or null) per song, in order. At most 50 songs. */
export async function getYoutubeIds(songs) {
  return postJSON("/map/youtube-ids", { songs });
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
export async function importLibrary(files, { enrich = true, listen = true, listenLimit = null, limit = null } = {}) {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  form.append("enrich", enrich ? "true" : "false");
  form.append("listen", listen ? "true" : "false");
  if (listenLimit) form.append("listen_limit", String(listenLimit));
  if (limit) form.append("limit", String(limit));
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

// --- Shared song stats (listener corrections) --------------------------------

/** GET /community/song — a song's looked-up stats, what listeners agreed on, and your own edits. */
export async function getSongStats({ artist, title }) {
  const q = new URLSearchParams({ artist: artist || "", title: title || "" });
  return apiFetch(`/community/song?${q}`);
}

/** POST /community/vote — value null takes your earlier answer back. */
export async function voteSongStat({ artist, title, field, value }) {
  return postJSON("/community/vote", { artist: artist || "", title, field, value });
}

/** GET /community/activity */
export async function getCommunityActivity(limit = 20) {
  return apiFetch(`/community/activity?limit=${limit}`);
}

/** POST /map/taste-match — public shared maps closest to this library. */
export async function tasteMatch({ csv_path, sample = false, share_id, limit = 10 }) {
  return postJSON("/map/taste-match", { csv_path, sample, share_id, limit });
}

// --- Accounts, people and the feed -------------------------------------------

/** Remember which library is "my map" in this browser (and on the account when signed in). */
export function rememberMyMap({ csv_path, title }) {
  try {
    window.localStorage.setItem("sm-my-map", JSON.stringify({ csv_path, title, at: Date.now() }));
  } catch {
    // private window: Compare will ask for the library again
  }
  apiFetch("/me/library", { method: "PUT", body: JSON.stringify({ csv_path, title }) }).catch(() => {});
}

export function myMap() {
  try {
    return JSON.parse(window.localStorage.getItem("sm-my-map") || "null");
  } catch {
    return null;
  }
}

export const getProfile = (username) => apiFetch(`/users/${encodeURIComponent(username)}`);
export const updateProfile = (patch) => apiFetch("/auth/me", { method: "PATCH", body: JSON.stringify(patch) });
export const followUser = (username, on = true) => postJSON(`/users/${encodeURIComponent(username)}/follow`, { on });
export const followList = (username, which) => apiFetch(`/users/${encodeURIComponent(username)}/${which}`);
export const searchPeople = (q) => apiFetch(`/users?q=${encodeURIComponent(q)}`);
export const getFeed = (before) => apiFetch(`/feed${before ? `?before=${before}` : ""}`);
export const getDigest = () => apiFetch("/digest");
export const getLeaderboards = () => apiFetch("/leaderboards");
export const setMapListed = (id, listed) => postJSON(`/map/shared/${encodeURIComponent(id)}/listed`, { listed });

/** The 1200x630 share card of a shared map. */
export const sharedMapCard = (id) => `${API_BASE}/map/shared/${encodeURIComponent(id)}/card.png`;

/** Two libraries as one map; each track has who: "you" | "them" | "both", plus a `blend` summary. */
export const blendMaps = ({ mine, theirs, weights = {} }) => postJSON("/map/blend", { mine, theirs, weights });

/** Count a Map Radio station for the weekly charts. */
export const radioPlayed = ({ station, label, share_id }) => postJSON("/map/radio/played", { station, label, share_id }).catch(() => {});

// --- Community atlas ---------------------------------------------------------

export const getAtlas = () => apiFetch("/atlas");
export const atlasMine = (source) => postJSON("/atlas/mine", source);
export const atlasSong = (song_key) => apiFetch(`/atlas/song?song_key=${encodeURIComponent(song_key)}`);
export const atlasPins = () => apiFetch("/atlas/pins");
export const addAtlasPin = ({ song_key, text, title }) => postJSON("/atlas/pins", { song_key, text, title });
export const deleteAtlasPin = (id) => apiFetch(`/atlas/pins/${id}`, { method: "DELETE" });

// --- Artists -----------------------------------------------------------------

export async function landTrack(file, { title, artist_name, genre, public: isPublic }) {
  const form = new FormData();
  form.append("file", file);
  form.append("title", title);
  if (artist_name) form.append("artist_name", artist_name);
  if (genre) form.append("genre", genre);
  form.append("public", isPublic ? "true" : "false");
  return apiFetch("/artist/land", { method: "POST", body: form });
}
export const setTrackPublic = (id, isPublic) => postJSON(`/artist/tracks/${encodeURIComponent(id)}`, { public: isPublic });
export const deleteTrack = (id) => apiFetch(`/artist/tracks/${encodeURIComponent(id)}`, { method: "DELETE" });

// --- Games -------------------------------------------------------------------

export const quizQuestion = () => apiFetch("/games/quiz");
export const quizAnswer = (id, choice) => postJSON("/games/quiz/answer", { id, choice });
export const quizFinish = (name) => postJSON("/games/quiz/finish", { name });
