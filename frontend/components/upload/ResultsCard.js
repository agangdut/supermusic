"use client";

import ThemedCard from "./ThemedCard";
import PrimaryButton from "./PrimaryButton";
import ResultsPanel from "../jobs/ResultsPanel";
import ResultsConsole from "../jobs/ResultsConsole";

export default function ResultsCard({
  busy,
  jobs,
  clearJobs,
  retryJob,
  latestMidi,
  latestStems,
  latestCsv,
  onStemsToMidi,
}) {
  return (
    <div className="space-y-6">
      <ThemedCard
        title="Jobs"
        desc="All tasks you've run this session."
        rightSlot={
          <PrimaryButton
            onClick={clearJobs}
            disabled={busy || jobs.length === 0}
            className={
              (busy || jobs.length === 0)
                ? "opacity-50 cursor-not-allowed"
                : ""
            }
          >
            Clear
          </PrimaryButton>
        }
      >
        <ResultsPanel jobs={jobs} onRetry={retryJob} />
      </ThemedCard>

      {(latestMidi || latestStems || latestCsv) && (
        <ThemedCard
          title="Latest Results"
          desc="Most recent artifacts from completed jobs."
        >
          <ResultsConsole
            latestMidi={latestMidi}
            latestStems={latestStems}
            latestCsv={latestCsv}
            onStemsToMidi={onStemsToMidi}
            busy={busy}
          />
        </ThemedCard>
      )}
    </div>
  );
}
