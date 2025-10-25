"use client";

import ThemedCard from "./ThemedCard";
import PrimaryButton from "./PrimaryButton";
import ResultsConsole from "../jobs/ResultsConsole";

export default function ResultsCard({
  busy,
  jobs,
  clearJobs,
  latestMidi,
  latestStems,
  latestCsv,
}) {
  return (
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
      <ResultsConsole
        latestMidi={latestMidi}
        latestStems={latestStems}
        latestCsv={latestCsv}
      />
    </ThemedCard>
  );
}
