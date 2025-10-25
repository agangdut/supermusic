"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";
const api = (path) => (API_BASE ? `${API_BASE}${path}` : `/api${path}`);
const isTerminal = (s) => ["done", "error", "cancelled"].includes(s);

async function fetchJSON(input, init) {
  const res = await fetch(input, init);
  const isJSON = res.headers.get("content-type")?.includes("application/json");
  if (!res.ok) {
    const text = isJSON ? JSON.stringify(await res.json()) : await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return isJSON ? res.json() : res.text();
}

export default function useUploadJobs() {
  const [audioFile, setAudioFile] = useState(null);
  const [csvFile, setCsvFile] = useState(null);

  const [jobs, setJobs] = useState([]);
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);

  const [latestMidi, setLatestMidi] = useState(null);
  const [latestStems, setLatestStems] = useState(null);
  const [latestCsv, setLatestCsv] = useState(null);

  const runningRef = useRef(false);

  const runningCount = useMemo(
    () => jobs.filter((j) => !isTerminal(j.status)).length,
    [jobs]
  );

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

  // polling unfinished jobs
  useEffect(() => {
    if (!jobs.some((j) => !isTerminal(j.status))) return;

    const handle = setInterval(async () => {
      try {
        const next = await Promise.all(
          jobs.map(async (j) => {
            if (isTerminal(j.status) || !j.id) return j;
            try {
              const data = await fetchJSON(api(`/jobs/${j.id}`));
              return { ...j, ...data };
            } catch {
              return j;
            }
          })
        );
        setJobs(next);
      } catch {
        // swallow
      }
    }, 2000);

    return () => clearInterval(handle);
  }, [jobs]);

  // generic uploader
  const handleUpload = useCallback(
    async (type, file, endpoint, successMsg, failMsg, onSuccessData) => {
      if (!file) {
        notify("Please select a file first.", "warn");
        return;
      }
      if (runningRef.current) return;

      runningRef.current = true;
      setBusy(true);

      const jobId = pushJob(type, `Uploading ${type}…`);

      try {
        const fd = new FormData();
        fd.append("file", file);

        const data = await fetchJSON(api(endpoint), {
          method: "POST",
          body: fd,
        });

        updateJob(jobId, {
          status: "done",
          message: successMsg,
          result: data,
        });

        if (onSuccessData) onSuccessData(data);

        notify(successMsg, "ok");
      } catch (err) {
        updateJob(jobId, {
          status: "error",
          message: failMsg,
          error_detail: String(err),
        });
        notify(failMsg, "err");
      } finally {
        runningRef.current = false;
        setBusy(false);
      }
    },
    [notify, pushJob, updateJob]
  );

  // public actions
  const transcribeMidi = useCallback(() => {
    handleUpload(
      "transcription",
      audioFile,
      "/midi/transcribe",
      "Transcription complete 🎹",
      "Transcription failed ❌",
      (data) => setLatestMidi(data)
    );
  }, [audioFile, handleUpload]);

  const separateStems = useCallback(() => {
    handleUpload(
      "separation",
      audioFile,
      "/audio/separate",
      "Stem separation complete 🎛️",
      "Stem separation failed ❌",
      (data) => setLatestStems(data)
    );
  }, [audioFile, handleUpload]);

  const enrichCsv = useCallback(() => {
    handleUpload(
      "metadata",
      csvFile,
      "/csv/enrich",
      "CSV enrichment complete ✅",
      "CSV enrichment failed ❌",
      (data) => setLatestCsv(data)
    );
  }, [csvFile, handleUpload]);

  const clearJobs = useCallback(() => {
    setJobs([]);
  }, []);

  return {
    // state
    audioFile,
    csvFile,
    jobs,
    toast,
    busy,
    runningCount,
    latestMidi,
    latestStems,
    latestCsv,

    // setters for inputs
    setAudioFile,
    setCsvFile,

    // actions
    transcribeMidi,
    separateStems,
    enrichCsv,
    clearJobs,
  };
}
