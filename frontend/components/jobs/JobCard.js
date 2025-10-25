"use client";
import React from "react";
import ProgressBar from "./ProgressBar";
import ArtifactList from "./ArtifactList";

const STATUS_STYLES = {
  queued:   "bg-gray-100 text-gray-800",
  running:  "bg-blue-100 text-blue-800",
  success:  "bg-green-100 text-green-800",
  failed:   "bg-red-100 text-red-800",
  canceled: "bg-amber-100 text-amber-800",
};

const TYPE_LABELS = {
  midi_conversion: "MIDI Conversion",
  csv_enrichment: "CSV Enrichment",
  stem_separation: "Stem Separation",
  track_download: "Track Download",
};

function StatusBadge({ status }) {
  const cls = STATUS_STYLES[status] || STATUS_STYLES.queued;
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs ${cls}`}>
      {status}
    </span>
  );
}

function formatWhen(ts) {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    return d.toLocaleString();
  } catch {
    return String(ts);
  }
}

export default function JobCard({
  job,
  onUseArtifact,   // optional: (key, url) => void
  className = "",
}) {
  const {
    id,
    job_type,
    status,
    message,
    progress = 0,
    created_at,
    result,
    error,
  } = job || {};

  const typeLabel = TYPE_LABELS[job_type] || job_type || "Job";

  return (
    <article className={`rounded-xl border bg-white p-3 shadow-sm ${className}`}>
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate font-medium">{typeLabel}</h3>
            <StatusBadge status={status} />
          </div>
          <p className="mt-0.5 text-xs text-gray-500">Created: {formatWhen(created_at)}</p>
          <p className="mt-0.5 text-sm text-gray-700">{message || "\u00A0"}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-[10px] text-gray-400">ID</p>
          <p className="text-[11px] text-gray-600 font-mono truncate max-w-[160px]" title={id}>{id}</p>
        </div>
      </header>

      {status && ["running", "queued"].includes(status) && (
        <div className="mt-3">
          <ProgressBar value={progress || 0} srLabel={`${typeLabel} progress`} />
          <p className="mt-1 text-xs text-gray-500">{Math.round(progress || 0)}%</p>
        </div>
      )}

      {status === "failed" && error && (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {result?.artifacts && (
        <ArtifactList
          className="mt-3"
          artifacts={result.artifacts}
          onUse={onUseArtifact}
        />
      )}

      {result?.metrics && (
        <details className="mt-3 group">
          <summary className="cursor-pointer text-sm text-gray-600 group-open:text-gray-800">
            Metrics
          </summary>
          <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-gray-50 p-3 text-xs text-gray-800">
            {JSON.stringify(result.metrics, null, 2)}
          </pre>
        </details>
      )}
    </article>
  );
}
