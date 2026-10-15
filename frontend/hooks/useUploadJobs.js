"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiFetch, API_BASE } from "@/utils/fetcher";
import { setBackgroundWork } from "@/lib/backgroundWork";
import { midiConvert, stemsSeparate, csvEnrich, enrichFiles, getJob, areaForJobType, normalizeJobArtifacts, toArtifactUrl } from "@/lib/api";

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
  if (t === "csv_enrichment") return "CSV enrichment";
  if (t === "track_download") return "Download";
  return "Job";
};


// MIDI files as URLs, plus the melody score when the job measured one
const midiResult = (result) => ({
  ...normalizeJobArtifacts({ result }).result.artifacts,
  melody: result?.metrics?.melody,
});

// The CSV result: download link, the server path the Music Map can open, and what was done
const csvResult = (result) => ({
  url: toArtifactUrl(result?.artifacts?.csv),
  library_csv: result?.library_csv || null,
  metrics: result?.metrics || null,
});

const STORAGE_KEY = "supermusic.workspace";

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
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
      if (saved) {
        setJobs((saved.jobs || []).filter((j) => j.job_type || isTerminal(j.status)));
        setLatestMidi(saved.latestMidi || null);
        setLatestStems(saved.latestStems || null);
        setLatestStemsJobId(saved.latestStemsJobId || null);
        setLatestCsv(saved.latestCsv || null);
      }
    } catch { /* storage blocked or corrupt: start fresh */ }
    setRestored(true);
  }, []);
  useEffect(() => {
    if (!restored) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ jobs, latestMidi, latestStems, latestStemsJobId, latestCsv }));
    } catch { /* storage full or blocked: not critical */ }
  }, [restored, jobs, latestMidi, latestStems, latestStemsJobId, latestCsv]);

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
        setLatestMidi(midiResult(data.result));
      } else if (j.job_type === "stem_separation") {
        setLatestStems(normalizeJobArtifacts({ result: { artifacts } }).result.artifacts);
        setLatestStemsJobId(j.id);
      } else if (j.job_type === "csv_enrichment" && artifacts.csv) {
        setLatestCsv(csvResult(data.result));
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

        // Update job with backend job data
        updateJob(jobId, {
          id: job.id,
          job_type: job.job_type || job.type,
          status: mappedJob.status,
          message: job.message,
          progress: job.progress,
          result: job.result,
          error_detail: job.error_detail,
        });

        // Replace the local job with the backend job
        setJobs((prev) => prev.map((j) => (j.id === jobId ? { ...j, ...mappedJob, id: job.id } : j)));

        // If job is already done, handle success
        if ((job.status === "done" || mappedJob.status === "success") && job.result) {
          if (onSuccessData) onSuccessData(job.result);
          notify(successMsg, "ok");
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
            ? "Couldn't reach the SuperMusic server. Is Docker running? Try: docker compose up -d"
            : undefined,
        });
        notify(failMsg, "err");
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
        csv_enrichment: p.csv_path ? () => csvEnrich(p) : null,
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
        (result) => {
          if (result?.artifacts?.midi) {
            setLatestMidi(midiResult(result));
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
      (result) => {
        if (result?.artifacts?.midi) {
          setLatestMidi(midiResult(result));
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
        (result) => {
          if (result?.artifacts) {
            setLatestStems(normalizeJobArtifacts({ result }).result.artifacts);
          }
        }
      );
    } catch (err) {
      notify(`Stem separation failed: ${err.message}`, "err");
    } finally {
      setBusy(false);
    }
  }, [audioFile, uploadFile, createJob, notify]);

  const enrichCsv = useCallback(async ({ lookup = true, limit } = {}) => {
    if (!csvFiles.length) {
      notify("Please choose at least one file first.", "warn");
      return;
    }
    // Files go up with the request; the server merges them and runs the job
    notify(`Uploading ${csvFiles.length} file${csvFiles.length > 1 ? "s" : ""}…`, "info");
    await createJob(
      "csv_enrichment",
      () => enrichFiles(csvFiles, { lookup, limit }),
      "CSV enrichment complete ✅",
      "CSV enrichment failed ❌",
      (result) => {
        if (result?.artifacts?.csv) setLatestCsv(csvResult(result));
      }
    );
  }, [csvFiles, createJob, notify]);

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
    clearJobs,
  };
}
