"use client";

import ThemedCard from "./ThemedCard";

export default function StatusCard({ runningCount }) {
  return (
    <ThemedCard
      title="Status"
      desc="Quick glance at current workload and queue."
      rightSlot={
        <span className="text-xs text-gray-400">
          Active:{" "}
          <span className="text-white font-semibold">
            {runningCount}
          </span>
        </span>
      }
    >
      <p className="text-sm text-gray-400 leading-snug">
        We automatically poll running jobs every 2s.
      </p>
    </ThemedCard>
  );
}
