"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiFetch, API_BASE } from "@/utils/fetcher";
import { setBackgroundWork } from "@/lib/backgroundWork";
import { useAuth, WORKSPACE_KEY } from "@/lib/auth";
import { midiConvert, stemsSeparate, csvEnrich, enrichFiles, importLastfm, getJob, areaForJobType, normalizeJobArtifacts, toArtifactUrl } from "@/lib/api";

// Map backend status to frontend status
const mapStatus = (status) => {
  const mapping = {
    "queued": "queued",
    "running": "running",
    "done": "success",
    "error": "failed",
    "cancelled": "canceled",
  };
  return mapping[status] || status;
};

const isTerminal = (s) => ["success", "failed", "canceled", "done", "error"].includes(s);

const MODE_LABELS = { auto: "Auto", multi: "Full band", stems: "Stems", piano: "Piano", basic: "General", cover: "Piano cover" };
export const jobLabel = (j) => {
  const t = j.job_type || j.type;
  if (t === "midi_conversion") return `MIDI (${MODE_LABELS[j.payload?.model] || "General"})`;
  if (t === "stem_separation") return "Stem separation";
  if (t === "csv_enrichment") return j.payload?.source === "lastfm" ? `Last.fm import (${j.payload.username})` : "CSV enrichment";
  if (t === "track_download") return "Download";
  return "Job";
};


// MIDI files as URLs, plus the melody score when the job measured one.
// jobId ties a result to its job, so it goes away when the server forgets the job.
const midiResult = (result, jobId) => ({
  ...normalizeJobArtifacts({ result }).result.artifacts,
  melody: result?.metrics?.melody,
  jobId,
});

// The CSV result: download link, the server path the Music Map can open, and what was done
const csvResult = (result, jobId) => ({
  url: toArtifactUrl(result?.artifacts?.csv),
  zip: toArtifactUrl(result?.artifacts?.zip),
  library_csv: result?.library_csv || null,
  metrics: result?.metrics || null,
  jobId,
});

// Signed in: jobs stay in localStorage. Signed out: sessionStorage, cleared when the browser closes.
const workspaceStore = (signedIn) => {
  try {
    return signedIn ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
};
const otherStore = (signedIn) => workspaceStore(!signedIn);

// Does the server still have this job? Only a clear "not found" counts as gone.
const jobIsGone = async (j) => {
  const area = areaForJobType(j.job_type);
  if (!area) return false;
  try {
    await getJob(area, j.id);
    return false;
  } catch (err) {
    return /not found|404/i.test(String(err?.message || err));
  }
};

export default function useUploadJobs() {
  const [audioFile, setAudioFile] = useState(null);
  const [csvFiles, setCsvFiles] = useState([]);

  const [jobs, setJobs] = useState([]);
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);

  const [latestMidi, setLatestMidi] = useState(null);
  const [latestStems, setLatestStems] = useState(null);
  const [latestStemsJobId, setLatestStemsJobId] = useState(null);
  const [latestCsv, setLatestCsv] = useState(null);

  const runningRef = useRef(false);
  const { token, ready: authReady } = useAuth();
  const signedIn = !!token;

  const runningCount = useMemo(
    () => jobs.filter((j) => !isTerminal(j.status)).length,
    [jobs]
  );

  // Tell the "safe to switch" notice how many jobs are running
  useEffect(() => { setBackgroundWork("jobs", runningCount); }, [runningCount]);

  // Remember jobs and results in the browser, so a page refresh doesn't clear them.
  // Running jobs pick up polling again; ones that never got a server id are dropped.
  const [restored, setRestored] = useState(false);
  useEffect(() => {
    if (!authReady || restored) return;
    let saved = null;
    try {
      saved = JSON.parse(workspaceStore(signedIn)?.getItem(WORKSPACE_KEY) || "null");
      // Signed out: drop history an older version kept in localStorage
      if (!signedIn) otherStore(signedIn)?.removeItem(WORKSPACE_KEY);
    } catch { /* storage blocked or corrupt: start fresh */ }
    setRestored(true);
    if (!saved) return;

    const savedJobs = (saved.jobs || []).filter((j) => j.job_type || isTerminal(j.status));
    setJobs(savedJobs);
    setLatestMidi(saved.latestMidi || null);
    setLatestStems(saved.latestStems || null);
    setLatestStemsJobId(saved.latestStemsJobId || null);
    setLatestCsv(saved.latestCsv || null);

    // Ask the server about every saved job once, and drop the ones it no longer has
    // (it was reset, or cleaned up old jobs), along with their results
    (async () => {
      const toCheck = new Map(savedJobs.filter((j) => j.id && j.job_type).map((j) => [j.id, j]));
      // Results can outlive a cleared job list, so check their jobs too
      for (const [id, job_type] of [
        [saved.latestMidi?.jobId, "midi_conversion"],
        [saved.latestCsv?.jobId, "csv_enrichment"],
        [saved.latestStemsJobId, "stem_separation"],
      ]) if (id && !toCheck.has(id)) toCheck.set(id, { id, job_type });
      const checks = await Promise.all([...toCheck.values()].map(async (j) => [j.id, await jobIsGone(j)]));
      const gone = new Set(checks.filter(([, g]) => g).map(([id]) => id));
      // Results saved before they carried a job id can't be checked, so they go too
      const keep = (id) => !!id && !gone.has(id);
      setJobs((prev) => prev.filter((j) => !gone.has(j.id)));
      setLatestMidi((r) => (r && keep(r.jobId) ? r : null));
      setLatestCsv((r) => (r && keep(r.jobId) ? r : null));
      if (!keep(saved.latestStemsJobId)) {
        setLatestStems(null);
        setLatestStemsJobId(null);
      }
    })();
  }, [authReady, restored, signedIn]);
  useEffect(() => {
    if (!restored) return;
    try {
      workspaceStore(signedIn)?.setItem(WORKSPACE_KEY, JSON.stringify({ jobs, latestMidi, latestStems, latestStemsJobId, latestCsv }));
      otherStore(signedIn)?.removeItem(WORKSPACE_KEY);
    } catch { /* storage full or blocked: not critical */ }
  }, [restored, signedIn, jobs, latestMidi, latestStems, latestStemsJobId, latestCsv]);

  // Signing out clears the Studio history (signOut() also wipes the saved copy)
  const wasSignedIn = useRef(null);
  useEffect(() => {
    if (!authReady) return;
    if (wasSignedIn.current && !signedIn) {
      setJobs([]);
      setLatestMidi(null);
      setLatestStems(null);
      setLatestStemsJobId(null);
      setLatestCsv(null);
    }
    wasSignedIn.current = signedIn;
  }, [authReady, signedIn]);

  // toast helper
  const notify = useCallback((msg, kind = "info") => {
    setToast({ msg, kind });
    setTimeout(() => setToast(null), 3500);
  }, []);

  // job helpers
  const pushJob = useCallback((type, message) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const j = {
      id,
      type,
      status: "running",
      message,
      created_at: new Date().toISOString(),
    };
    setJobs((prev) => [j, ...prev]);
    return id;
  }, []);

  const updateJob = useCallback((id, patch) => {
    setJobs((prev) =>
      prev.map((j) => (j.id === id ? { ...j, ...patch } : j))
    );
  }, []);

  // polling unfinished jobs and extracting artifacts when complete
  const handleFinished = useCallback((j, data) => {
    const artifacts = data.result?.artifacts;
    if (data.status === "done" && artifacts) {
      if (j.job_type === "midi_conversion" && artifacts.midi) {
        setLatestMidi(midiResult(data.result, j.id));
      } else if (j.job_type === "stem_separation") {
        setLatestStems(normalizeJobArtifacts({ result: { artifacts } }).result.artifacts);
        setLatestStemsJobId(j.id);
      } else if (j.job_type === "csv_enrichment" && (artifacts.csv || artifacts.zip)) {
        setLatestCsv(csvResult(data.result, j.id));
      }
    }
  }, []);

  useEffect(() => {
    if (!jobs.some((j) => !isTerminal(j.status))) return;

    const handle = setInterval(async () => {
      const next = await Promise.all(
        jobs.map(async (j) => {
          if (isTerminal(j.status) || !j.id || !j.job_type) return j;
          const area = areaForJobType(j.job_type);
          if (!area) return j;
          try {
            const data = await getJob(area, j.id);
            const status = mapStatus(data.status);
            if (isTerminal(status)) {
              handleFinished(j, data);
              if (status === "success") notify(`${jobLabel(j)} finished ✓`, "ok");
              else notify(`${jobLabel(j)} failed: ${data.error_hint || data.error_detail || "unknown error"}`, "err");
            }
            return { ...j, ...data, status, lastSeen: Date.now(), missedPolls: 0 };
          } catch (err) {
            const msg = String(err?.message || err);
            // The server answered, but doesn't know the job: it restarted and lost it
            if (/not found|404/i.test(msg)) {
              notify(`${jobLabel(j)} was lost when the server restarted.`, "err");
              return {
                ...j, status: "failed", lost: true,
                message: "Lost when the server restarted",
                error_hint: "The server restarted while this was running, so the job was lost. Start it again.",
              };
            }
            // Couldn't reach the server at all; keep the job, flag the connection
            return { ...j, missedPolls: (j.missedPolls || 0) + 1 };
          }
        })
      );
      setJobs(next);
    }, 2000);

    return () => clearInterval(handle);
  }, [jobs, handleFinished, notify]);

  // Show running jobs in the browser tab title, so you can switch away and still see it
  useEffect(() => {
    const base = "SuperMusic";
    const running = jobs.filter((j) => !isTerminal(j.status)).length;
    document.title = running ? `⏳ ${running} job${running > 1 ? "s" : ""} running · ${base}` : base;
    return () => { document.title = base; };
  }, [jobs]);

  // upload file and return server path
  const uploadFile = useCallback(async (file, fileType = "audio") => {
    const endpoint = fileType === "audio" ? "/upload/audio" : "/upload/csv";
    const formData = new FormData();
    formData.append("file", file);

    const response = await apiFetch(endpoint, {
      method: "POST",
      body: formData,
    });

    if (!response.success || !response.path) {
      throw new Error(response.detail || "Upload failed");
    }

    return response.path;
  }, []);

  // generic job creator
  const createJob = useCallback(
    async (type, jobCreatorFn, successMsg, failMsg, onSuccessData) => {
      if (runningRef.current) return;

      runningRef.current = true;
      setBusy(true);

      const jobId = pushJob(type, `Starting ${type}…`);

      try {
        const job = await jobCreatorFn();
        
        // Map backend status to frontend status
        const mappedJob = {
          ...job,
          status: mapStatus(job.status),
        };

        // Replace the local placeholder with the backend job (payload, error_hint and all,
        // so a job that already finished or failed on the server shows its real label and reason)
        updateJob(jobId, { ...mappedJob, id: job.id, job_type: job.job_type || job.type });

        // If job is already done, handle success
        if ((job.status === "done" || mappedJob.status === "success") && job.result) {
          if (onSuccessData) onSuccessData(job.result, job.id);
          notify(successMsg, "ok");
        } else if (mappedJob.status === "failed") {
          notify(`${failMsg}: ${job.error_hint || job.error_detail || "unknown error"}`, "err");
        } else {
          notify(`Job started: ${job.message || successMsg}`, "info");
        }
      } catch (err) {
        const detail = String(err?.message || err);
        updateJob(jobId, {
          status: "failed",
          message: failMsg,
          error_detail: detail,
          error_hint: /failed to fetch|networkerror|load failed/i.test(detail)
            ? "Couldn't reach the SuperMusic server. Check your connection and try again (running it yourself? docker compose up -d)."
            : /sign in/i.test(detail)
              ? "Sign in (top right) to run this. It's free."
              : undefined,
        });
        // Say why when it's something they can act on (sign in, a limit, a file that's gone)
        notify(/sign in|jobs|too many|minutes long|over \d+ MB|upload it again/i.test(detail) ? detail : failMsg, "err");
      } finally {
        runningRef.current = false;
        setBusy(false);
      }
    },
    [notify, pushJob, updateJob]
  );

  // Run a finished or failed job again with the same settings (no re-upload needed)
  const retryJob = useCallback(
    (j) => {
      const p = j.payload || {};
      const type = j.job_type || j.type;
      const run = {
        midi_conversion: () => midiConvert(p),
        stem_separation: () => stemsSeparate(p),
        // Batch jobs were sent as files, which the browser no longer has
        csv_enrichment: p.source === "lastfm" ? () => importLastfm(p) : p.csv_path ? () => csvEnrich(p) : null,
      }[type];
      if (!run) return notify("This job can't be retried. Start it again from the form.", "warn");
      setJobs((prev) => prev.filter((x) => x.id !== j.id));
      return createJob(type, run, `${jobLabel(j)} finished ✓`, `${jobLabel(j)} failed`);
    },
    [createJob, notify]
  );

  // public actions
  const transcribeMidi = useCallback(async (model = "auto", { playable = false, handSpan = 14, vocalTrack = true, stems } = {}) => {
    if (!audioFile) {
      notify("Please select an audio file first.", "warn");
      return;
    }

    try {
      // Step 1: Upload the audio file
      setBusy(true);
      notify("Uploading audio file…", "info");
      const audioPath = await uploadFile(audioFile, "audio");

      // Step 2: Create MIDI conversion job
      await createJob(
        "midi_conversion",
        () => midiConvert({
          source_path: audioPath, model, playable, hand_span: handSpan, vocal_track: vocalTrack,
          stems: model === "stems" ? stems : undefined,
        }),
        "Transcription complete 🎹",
        "Transcription failed ❌",
        (result, id) => {
          if (result?.artifacts?.midi) {
            setLatestMidi(midiResult(result, id));
          }
        }
      );
    } catch (err) {
      notify(`Transcription failed: ${err.message}`, "err");
    } finally {
      setBusy(false);
    }
  }, [audioFile, uploadFile, createJob, notify]);

  // Turn stems from the last separation into MIDI, without separating again
  const transcribeSeparatedStems = useCallback(async (stems, { playable = false, handSpan = 14 } = {}) => {
    if (!latestStemsJobId) {
      notify("Separate the stems first.", "warn");
      return;
    }
    if (!stems?.length) {
      notify("Pick at least one stem.", "warn");
      return;
    }
    await createJob(
      "midi_conversion",
      () => midiConvert({ stem_job_id: latestStemsJobId, model: "stems", stems, playable, hand_span: handSpan }),
      "Transcription complete 🎹",
      "Transcription failed ❌",
      (result, id) => {
        if (result?.artifacts?.midi) {
          setLatestMidi(midiResult(result, id));
        }
      }
    );
  }, [latestStemsJobId, createJob, notify]);

  const separateStems = useCallback(async () => {
    if (!audioFile) {
      notify("Please select an audio file first.", "warn");
      return;
    }

    try {
      // Step 1: Upload the audio file
      setBusy(true);
      notify("Uploading audio file…", "info");
      const audioPath = await uploadFile(audioFile, "audio");

      // Step 2: Create stem separation job
      await createJob(
        "stem_separation",
        () => stemsSeparate({ audio_path: audioPath }),
        "Stem separation complete 🎛️",
        "Stem separation failed ❌",
        (result, id) => {
          if (result?.artifacts) {
            setLatestStems(normalizeJobArtifacts({ result }).result.artifacts);
            setLatestStemsJobId(id);
          }
        }
      );
    } catch (err) {
      notify(`Stem separation failed: ${err.message}`, "err");
    } finally {
      setBusy(false);
    }
  }, [audioFile, uploadFile, createJob, notify]);

  const enrichCsv = useCallback(async ({ lookup = true, limit, output = "combined" } = {}) => {
    if (!csvFiles.length) {
      notify("Please choose at least one file first.", "warn");
      return;
    }
    // Files go up with the request; the server merges them and runs the job
    notify(`Uploading ${csvFiles.length} file${csvFiles.length > 1 ? "s" : ""}…`, "info");
    await createJob(
      "csv_enrichment",
      () => enrichFiles(csvFiles, { lookup, limit, output }),
      "CSV enrichment complete ✅",
      "CSV enrichment failed ❌",
      (result, id) => {
        if (result?.artifacts?.csv || result?.artifacts?.zip) setLatestCsv(csvResult(result, id));
      }
    );
  }, [csvFiles, createJob, notify]);

  // Read a library from Last.fm by username; the server enriches it in the background
  const importFromLastfm = useCallback(async (username, { lookup = true, limit } = {}) => {
    const name = String(username || "").trim();
    if (!name) {
      notify("Type your Last.fm username first.", "warn");
      return;
    }
    await createJob(
      "csv_enrichment",
      () => importLastfm({ username: name, lookup, limit }),
      "Last.fm import complete ✅",
      "Last.fm import failed ❌",
      (result, id) => {
        if (result?.artifacts?.csv) setLatestCsv(csvResult(result, id));
      }
    );
  }, [createJob, notify]);

  const clearJobs = useCallback(() => {
    setJobs([]);
  }, []);

  return {
    // state
    audioFile,
    csvFiles,
    jobs,
    toast,
    busy,
    runningCount,
    latestMidi,
    latestStems,
    latestStemsJobId,
    latestCsv,

    // setters for inputs
    setAudioFile,
    setCsvFiles,

    // actions
    transcribeMidi,
    retryJob,
    transcribeSeparatedStems,
    separateStems,
    enrichCsv,
    importFromLastfm,
    clearJobs,
  };
}
