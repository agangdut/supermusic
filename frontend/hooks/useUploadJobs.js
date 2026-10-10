"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiFetch, API_BASE } from "@/utils/fetcher";
import { midiConvert, stemsSeparate, csvEnrich, getJob, areaForJobType } from "@/lib/api";

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

  // polling unfinished jobs and extracting artifacts when complete
  useEffect(() => {
    if (!jobs.some((j) => !isTerminal(j.status))) return;

    const handle = setInterval(async () => {
      try {
        const next = await Promise.all(
          jobs.map(async (j) => {
            if (isTerminal(j.status) || !j.id || !j.job_type) return j;
            try {
              const area = areaForJobType(j.job_type);
              if (!area) return j;
              const data = await getJob(area, j.id);
              // Map backend status to frontend status
              const mappedData = {
                ...data,
                status: mapStatus(data.status),
              };
              
              // Extract artifacts when job completes
              if ((mappedData.status === "success" || data.status === "done") && data.result?.artifacts) {
                const artifacts = data.result.artifacts;
                if (j.job_type === "midi_conversion" && artifacts.midi) {
                  setLatestMidi(artifacts.midi);
                } else if (j.job_type === "stem_separation" && artifacts) {
                  setLatestStems(artifacts);
                } else if (j.job_type === "csv_enrichment" && artifacts.csv) {
                  setLatestCsv(artifacts.csv);
                }
              }
              
              return { ...j, ...mappedData };
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
  const transcribeMidi = useCallback(async () => {
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
        () => midiConvert({ source_path: audioPath }),
        "Transcription complete 🎹",
        "Transcription failed ❌",
        (result) => {
          if (result?.artifacts?.midi) {
            setLatestMidi(result.artifacts.midi);
          }
        }
      );
    } catch (err) {
      notify(`Transcription failed: ${err.message}`, "err");
    } finally {
      setBusy(false);
    }
  }, [audioFile, uploadFile, createJob, notify]);

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
            setLatestStems(result.artifacts);
          }
        }
      );
    } catch (err) {
      notify(`Stem separation failed: ${err.message}`, "err");
    } finally {
      setBusy(false);
    }
  }, [audioFile, uploadFile, createJob, notify]);

  const enrichCsv = useCallback(async () => {
    if (!csvFile) {
      notify("Please select a CSV file first.", "warn");
      return;
    }

    try {
      // Step 1: Upload the CSV file
      setBusy(true);
      notify("Uploading CSV file…", "info");
      const csvPath = await uploadFile(csvFile, "csv");

      // Step 2: Create CSV enrichment job
      await createJob(
        "csv_enrichment",
        () => csvEnrich({ csv_path: csvPath }),
        "CSV enrichment complete ✅",
        "CSV enrichment failed ❌",
        (result) => {
          if (result?.artifacts?.csv) {
            setLatestCsv(result.artifacts.csv);
          }
        }
      );
    } catch (err) {
      notify(`CSV enrichment failed: ${err.message}`, "err");
    } finally {
      setBusy(false);
    }
  }, [csvFile, uploadFile, createJob, notify]);

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
