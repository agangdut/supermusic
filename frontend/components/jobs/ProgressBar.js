"use client";
import React from "react";

/**
 * Accessible progress bar (0–100).
 */
export default function ProgressBar({
  value = 0,
  srLabel = "Progress",
  className = "",
}) {
  const pct = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  return (
    <div
      role="progressbar"
      aria-label={srLabel}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(pct)}
      className={`w-full h-2 rounded bg-gray-100 overflow-hidden ${className}`}
    >
      <div
        className="h-full bg-blue-500 transition-[width] duration-300"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
