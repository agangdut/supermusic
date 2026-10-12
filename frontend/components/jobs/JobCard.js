"use client";
import React, { useEffect, useRef, useState } from "react";
import ArtifactList from "./ArtifactList";
import { jobLabel } from "@/hooks/useUploadJobs";

const RUNNING = ["running", "queued"];
const FAILED = ["failed", "error"];

function fmtDuration(s) {
  if (s == null || !isFinite(s)) return "";
  s = Math.max(0, Math.round(s));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

// Backend times are UTC without a "Z"
const parseTime = (t) => (t ? new Date(/Z|[+-]\d\d:?\d\d$/.test(t) ? t : `${t}Z`).getTime() : null);

function Spinner({ className = "" }) {
  return (
    <span className={`inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-fuchsia-400/30 border-t-fuchsia-300 ${className}`} aria-hidden="true" />
  );
}

function StatusBadge({ status, lost, stalled }) {
  if (RUNNING.includes(status)) {
    return (
      <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${stalled ? "bg-amber-400/15 text-amber-200" : "bg-fuchsia-500/15 text-fuchsia-200"}`}>
        {stalled ? "⚠" : <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-fuchsia-400 opacity-75" /><span className="relative inline-flex h-2 w-2 rounded-full bg-fuchsia-400" /></span>}
        {stalled ? "Reconnecting" : "Working"}
      </span>
    );
  }
  if (FAILED.includes(status)) {
    return <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-[11px] font-medium text-red-200">{lost ? "Lost" : "Failed"}</span>;
  }
  if (status === "success" || status === "done") {
    return <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-200">Done</span>;
  }
  return <span className="rounded-full bg-white/10 px-2 py-0.5 text-[11px] text-gray-300">{status}</span>;
}

export default function JobCard({ job, onUseArtifact, onRetry, className = "" }) {
  const { status, message, progress = 0, created_at, started_at, finished_at, result, error_detail, error_hint,
    stage, stages = [], eta_s, lost, missedPolls = 0 } = job || {};
  const running = RUNNING.includes(status);
  const failed = FAILED.includes(status);
  const stalled = running && missedPolls >= 3;

  // Tick every second while running so the elapsed time and estimate move
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);

  const start = parseTime(started_at) || parseTime(created_at);
  const end = parseTime(finished_at);
  const elapsed = start ? ((running ? now : end || now) - start) / 1000 : null;
  const estimated = eta_s && elapsed != null ? Math.min(95, (elapsed / eta_s) * 100) : 0;
  // The estimate can grow mid-job (a slower step than expected); never move the bar backwards
  const maxPct = useRef(0);
  const pct = running
    ? (maxPct.current = Math.max(maxPct.current, progress || 0, estimated))
    : status === "success" || status === "done" ? 100 : progress || 0;
  const slow = running && eta_s && elapsed > eta_s * 1.5;
  const remaining = running && eta_s && elapsed != null ? eta_s - elapsed : null;
  const [showDetails, setShowDetails] = useState(false);

  return (
    <article className={`rounded-xl border p-3 ${failed ? "border-red-500/30 bg-red-500/[0.04]" : "border-white/10 bg-white/[0.03]"} ${className}`}>
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-sm font-semibold text-gray-100">{jobLabel(job)}</h3>
            <StatusBadge status={status} lost={lost} stalled={stalled} />
          </div>
          <p className="mt-1 flex items-center gap-2 text-xs text-gray-300">
            {running && !stalled && <Spinner />}
            <span className="truncate">{running ? stage || message || "Starting…" : message}</span>
          </p>
        </div>
        <div className="shrink-0 text-right text-[11px] tabular-nums text-gray-500">
          {elapsed != null && <div>{running ? `${fmtDuration(elapsed)} elapsed` : `took ${fmtDuration(elapsed)}`}</div>}
          {running && remaining != null && !slow && <div>{remaining > 5 ? `about ${fmtDuration(remaining)} left` : "finishing up…"}</div>}
        </div>
      </header>

      {running && (
        <div className="mt-3">
          <div className="h-1.5 overflow-hidden rounded-full bg-white/10" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
            <div
              className={`h-full rounded-full transition-[width] duration-1000 ease-linear ${stalled ? "bg-amber-400" : "bg-gradient-to-r from-fuchsia-500 to-indigo-500"} ${slow ? "animate-pulse" : ""}`}
              style={{ width: `${Math.max(3, pct)}%` }}
            />
          </div>
          <p className="mt-1.5 text-[11px] text-gray-500">
            {stalled
              ? "Can't reach the server right now. The job may still be running; retrying every 2 seconds…"
              : slow
                ? "Taking longer than usual, but still working. Long or busy songs can take a while."
                : "Running in the background. You can keep using the app, and the tab title shows when it's done."}
          </p>
        </div>
      )}

      {stages.length > 0 && (running || failed) && (
        <ol className="mt-3 space-y-1 text-[11px]">
          {stages.map((s, i) => {
            const current = running && i === stages.length - 1;
            const brokeHere = failed && i === stages.length - 1;
            const secs = s.ended_at ? (parseTime(s.ended_at) - parseTime(s.started_at)) / 1000 : current ? (now - parseTime(s.started_at)) / 1000 : null;
            return (
              <li key={i} className={`flex items-center gap-2 ${current ? "text-gray-100" : brokeHere ? "text-red-200" : "text-gray-500"}`}>
                <span className="w-3.5 text-center">{current ? <Spinner /> : brokeHere ? "✕" : "✓"}</span>
                <span className="flex-1 truncate">{s.label}</span>
                {secs != null && secs >= 1 && <span className="tabular-nums">{fmtDuration(secs)}</span>}
              </li>
            );
          })}
        </ol>
      )}

      {failed && (
        <div className="mt-3 rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2">
          <p className="text-sm text-red-100">{error_hint || "Something went wrong."}</p>
          <div className="mt-2 flex items-center gap-3">
            {onRetry && (
              <button onClick={() => onRetry(job)} className="rounded-md bg-red-400/20 px-2.5 py-1 text-xs font-medium text-red-50 hover:bg-red-400/30">
                Try again
              </button>
            )}
            {error_detail && (
              <button onClick={() => setShowDetails((v) => !v)} className="text-xs text-red-200/70 underline-offset-2 hover:underline">
                {showDetails ? "Hide" : "Show"} technical details
              </button>
            )}
          </div>
          {showDetails && (
            <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-black/30 p-2 text-[11px] text-red-100/80">{error_detail}</pre>
          )}
        </div>
      )}

      {result?.artifacts && <ArtifactList className="mt-3" artifacts={result.artifacts} onUse={onUseArtifact} />}

      {result?.metrics && (
        <details className="group mt-2">
          <summary className="cursor-pointer text-[11px] text-gray-500 group-open:text-gray-300">Details</summary>
          <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-black/30 p-3 text-[11px] text-gray-300">
            {JSON.stringify(result.metrics, null, 2)}
          </pre>
        </details>
      )}
    </article>
  );
}
