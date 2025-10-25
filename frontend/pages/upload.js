// frontend/pages/upload.js
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import PageShell from "@/components/layout/PageShell";

// ----- small helpers ---------------------------------------------------------
const API_BASE = process.env.NEXT_PUBLIC_API_URL || ""; // if you added next.config rewrites, leave this empty

const api = (path) => {
  // If API_BASE is set, hit e.g. http://127.0.0.1:8000/csv/enrich
  // Otherwise use Next rewrite like /api/csv/enrich -> http://127.0.0.1:8000/csv/enrich
  if (!path.startsWith("/")) path = "/" + path;
  return API_BASE ? `${API_BASE}${path}` : `/api${path}`;
};

async function fetchJSON(input, init) {
  const res = await fetch(input, init);
  const isJSON = res.headers.get("content-type")?.includes("application/json");
  if (!res.ok) {
    const text = isJSON ? JSON.stringify(await res.json()) : await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return isJSON ? res.json() : res.text();
}

const isTerminal = (s) => s === "done" || s === "error" || s === "cancelled";

// ----- page ------------------------------------------------------------------
export default function UploadPage() {
  // local state
  const [audioFile, setAudioFile] = useState(null);
  const [csvFile, setCsvFile] = useState(null);
  const [jobs, setJobs] = useState([]); // always an array
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState(null);

  // refs (avoid double submits)
  const runningRef = useRef(false);

  // derived values (guard for non-arrays anyway)
  const runningCount = useMemo(
    () => (Array.isArray(jobs) ? jobs.filter((j) => !isTerminal(j?.status)).length : 0),
    [jobs]
  );

  // poller stub (optional: if your backend exposes /jobs/:id)
  useEffect(() => {
    if (!jobs.some((j) => !isTerminal(j.status))) return;

    const id = setInterval(async () => {
      try {
        const next = await Promise.all(
          jobs.map(async (j) => {
            if (isTerminal(j.status) || !j.id) return j;
            try {
              const data = await fetchJSON(api(`/jobs/${j.id}`));
              return { ...j, ...data };
            } catch {
              return j; // ignore polling errors
            }
          })
        );
        setJobs(next);
      } catch {
        /* noop */
      }
    }, 2000);

    return () => clearInterval(id);
  }, [jobs]);

  // ui helpers
  const pushJob = (partial) => {
    const j = {
      id: partial.id || `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      type: partial.type || "unknown",
      status: partial.status || "running",
      message: partial.message || "",
      progress: partial.progress ?? null,
      result: partial.result ?? null,
      error_detail: partial.error_detail ?? null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    setJobs((prev) => [j, ...prev]);
    return j.id;
  };

  const updateJob = (id, patch) =>
    setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, ...patch, updated_at: new Date().toISOString() } : j)));

  const notify = (msg, kind = "info") => {
    setToast({ msg, kind });
    setTimeout(() => setToast(null), 3500);
  };

  // actions -------------------------------------------------------------------
  const onEnrichCsv = async () => {
    if (!csvFile) return notify("Select a CSV file first.", "warn");
    if (runningRef.current) return;
    runningRef.current = true;
    setBusy(true);

    const jobId = pushJob({ type: "metadata", status: "running", message: "Uploading CSV…" });

    try {
      const fd = new FormData();
      fd.append("file", csvFile);
      // Adjust endpoint to match your backend route (example: /csv/enrich)
      const data = await fetchJSON(api("/csv/enrich"), { method: "POST", body: fd });
      updateJob(jobId, { status: "done", message: "CSV enriched.", result: data });
      notify("CSV enrichment complete ✅", "ok");
    } catch (err) {
      updateJob(jobId, { status: "error", error_detail: String(err), message: "CSV enrichment failed." });
      notify("CSV enrichment failed ❌", "err");
    } finally {
      setBusy(false);
      runningRef.current = false;
    }
  };

  const onSeparateStems = async () => {
    if (!audioFile) return notify("Select an audio file first.", "warn");
    if (runningRef.current) return;
    runningRef.current = true;
    setBusy(true);

    const jobId = pushJob({ type: "separation", status: "running", message: "Uploading audio…" });

    try {
      const fd = new FormData();
      fd.append("file", audioFile);
      // Adjust to your backend route (example: /audio/separate)
      const data = await fetchJSON(api("/audio/separate"), { method: "POST", body: fd });
      updateJob(jobId, { status: "done", message: "Stems ready.", result: data });
      notify("Stem separation complete 🎛️", "ok");
    } catch (err) {
      updateJob(jobId, { status: "error", error_detail: String(err), message: "Stem separation failed." });
      notify("Stem separation failed ❌", "err");
    } finally {
      setBusy(false);
      runningRef.current = false;
    }
  };

  const onTranscribeMidi = async () => {
    if (!audioFile) return notify("Select an audio file first.", "warn");
    if (runningRef.current) return;
    runningRef.current = true;
    setBusy(true);

    const jobId = pushJob({ type: "transcription", status: "running", message: "Uploading audio…" });

    try {
      const fd = new FormData();
      fd.append("file", audioFile);
      // Adjust to your backend route (example: /midi/transcribe)
      const data = await fetchJSON(api("/midi/transcribe"), { method: "POST", body: fd });
      updateJob(jobId, { status: "done", message: "MIDI ready.", result: data });
      notify("Transcription complete 🎹", "ok");
    } catch (err) {
      updateJob(jobId, { status: "error", error_detail: String(err), message: "Transcription failed." });
      notify("Transcription failed ❌", "err");
    } finally {
      setBusy(false);
      runningRef.current = false;
    }
  };

  // render --------------------------------------------------------------------
  return (
    <PageShell>
      {/* Toast */}
      {toast && (
        <div
          className={
            "mb-4 rounded border px-4 py-2 " +
            (toast.kind === "ok"
              ? "bg-green-50 border-green-300 text-green-800"
              : toast.kind === "err"
              ? "bg-red-50 border-red-300 text-red-800"
              : toast.kind === "warn"
              ? "bg-yellow-50 border-yellow-300 text-yellow-900"
              : "bg-blue-50 border-blue-300 text-blue-900")
          }
        >
          {toast.msg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: actions */}
        <section className="lg:col-span-1 space-y-6">
          <div className="bg-white shadow rounded p-4">
            <h2 className="text-lg font-semibold mb-3">Audio</h2>
            <input
              type="file"
              accept="audio/*"
              onChange={(e) => setAudioFile(e.target.files?.[0] || null)}
              className="block w-full"
            />
            <div className="flex gap-2 mt-3">
              <button
                onClick={onTranscribeMidi}
                className="px-3 py-2 rounded bg-indigo-600 text-white disabled:opacity-50"
                disabled={!audioFile || busy}
              >
                Transcribe → MIDI
              </button>
              <button
                onClick={onSeparateStems}
                className="px-3 py-2 rounded bg-slate-700 text-white disabled:opacity-50"
                disabled={!audioFile || busy}
              >
                Separate Stems
              </button>
            </div>
          </div>

          <div className="bg-white shadow rounded p-4">
            <h2 className="text-lg font-semibold mb-3">CSV</h2>
            <input
              type="file"
              accept=".csv"
              onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
              className="block w-full"
            />
            <div className="flex gap-2 mt-3">
              <button
                onClick={onEnrichCsv}
                className="px-3 py-2 rounded bg-emerald-600 text-white disabled:opacity-50"
                disabled={!csvFile || busy}
              >
                Enrich CSV
              </button>
            </div>
          </div>

          <div className="bg-white shadow rounded p-4">
            <h2 className="text-lg font-semibold">Status</h2>
            <p className="text-sm text-gray-600">
              Running jobs: <span className="font-semibold">{runningCount}</span>
            </p>
          </div>
        </section>

        {/* Right: results */}
        <section className="lg:col-span-2">
          <div className="bg-white shadow rounded overflow-hidden">
            <header className="px-4 py-3 border-b flex items-center justify-between">
              <h2 className="text-lg font-semibold">Jobs</h2>
              <button
                onClick={() => setJobs([])}
                className="text-sm px-2 py-1 rounded border border-gray-300 hover:bg-gray-50"
                disabled={busy || jobs.length === 0}
              >
                Clear
              </button>
            </header>

            <div className="divide-y">
              {(Array.isArray(jobs) ? jobs : []).map((j) => (
                <article key={j.id} className="px-4 py-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <JobBadge type={j.type} />
                      <span className="text-sm text-gray-500">#{j.id.slice(-6)}</span>
                    </div>
                    <StatusPill status={j.status} />
                  </div>

                  {j.message && <p className="mt-1 text-sm text-gray-700">{j.message}</p>}

                  {j.result && (
                    <pre className="mt-2 text-xs bg-gray-50 p-2 rounded border overflow-x-auto">
                      {JSON.stringify(j.result, null, 2)}
                    </pre>
                  )}

                  {j.error_detail && (
                    <pre className="mt-2 text-xs bg-red-50 p-2 rounded border border-red-200 text-red-800 overflow-x-auto">
                      {j.error_detail}
                    </pre>
                  )}
                </article>
              ))}

              {jobs.length === 0 && (
                <div className="px-4 py-8 text-sm text-gray-600">No jobs yet — try an action on the left.</div>
              )}
            </div>
          </div>
        </section>
      </div>
    </PageShell>
  );
}

// ----- tiny UI bits ----------------------------------------------------------
function JobBadge({ type }) {
  const map = {
    transcription: "🎹 MIDI",
    separation: "🎛️ Stems",
    metadata: "🧩 CSV",
    visualization: "📈 Viz",
    download: "⬇️ Download",
  };
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded bg-gray-100 border">
      {map[type] || "Job"} <em className="not-italic text-gray-500">({type})</em>
    </span>
  );
}

function StatusPill({ status }) {
  const styles =
    status === "done"
      ? "bg-green-100 text-green-800 border-green-300"
      : status === "error"
      ? "bg-red-100 text-red-800 border-red-300"
      : "bg-yellow-100 text-yellow-800 border-yellow-300";
  return (
    <span className={`px-2 py-0.5 text-xs rounded border ${styles}`}>
      {status?.toUpperCase?.() ?? "UNKNOWN"}
    </span>
  );
}
