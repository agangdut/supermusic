"use client";
import React from "react";
import JobCard from "./JobCard";

/**
 * ResultsPanel renders a list of jobs (newest first recommended).
 */
export default function ResultsPanel({
  jobs = [],
  onUseArtifact,   // optional: passed down to JobCard
  onRetry,         // optional: (job) => void, shows "Try again" on failed jobs
  className = "",
  emptyState = "No jobs yet. Kick off a task to see results here.",
}) {
  if (!jobs.length) {
    return (
      <div className={`rounded-xl border border-white/10 bg-white/[0.03] p-6 text-center text-sm text-gray-400 ${className}`}>
        {emptyState}
      </div>
    );
  }

  return (
    <div className={`grid gap-3 ${className}`}>
      {jobs.map((j) => (
        <JobCard key={j.id} job={j} onUseArtifact={onUseArtifact} onRetry={onRetry} />
      ))}
    </div>
  );
}
