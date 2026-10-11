"use client";

import PageShell from "@/components/layout/PageShell";
import useUploadJobs from "@/hooks/useUploadJobs";

import ToastBanner from "@/components/upload/ToastBanner";
import AudioCard from "@/components/upload/AudioCard";
import CsvCard from "@/components/upload/CsvCard";
import StatusCard from "@/components/upload/StatusCard";
import ResultsCard from "@/components/upload/ResultsCard"; // wraps ThemedCard+ResultsConsole

export default function UploadPage() {
  const {
    audioFile,
    csvFile,
    jobs,
    toast,
    busy,
    runningCount,
    latestMidi,
    latestStems,
    latestStemsJobId,
    latestCsv,
    setAudioFile,
    setCsvFile,
    transcribeMidi,
    transcribeSeparatedStems,
    separateStems,
    enrichCsv,
    clearJobs,
    retryJob,
  } = useUploadJobs();

  return (
    <PageShell>
      <ToastBanner toast={toast} />

      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white tracking-tight">
          Upload & Process
        </h1>
        <p className="text-gray-400 text-sm mt-1 max-w-prose leading-snug">
          Convert audio to MIDI, enrich CSV metadata, separate stems,
          and monitor job progress — all in one workflow.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="space-y-6 lg:col-span-1">
          <AudioCard
            audioFile={audioFile}
            setAudioFile={setAudioFile}
            transcribeMidi={transcribeMidi}
            separateStems={separateStems}
            busy={busy}
          />

          <CsvCard
            csvFile={csvFile}
            setCsvFile={setCsvFile}
            enrichCsv={enrichCsv}
            busy={busy}
          />

          <StatusCard runningCount={runningCount} />
        </div>

        <div className="lg:col-span-2">
          <ResultsCard
            busy={busy}
            jobs={jobs}
            clearJobs={clearJobs}
            latestMidi={latestMidi}
            latestStems={latestStems}
            latestCsv={latestCsv}
            retryJob={retryJob}
            onStemsToMidi={latestStemsJobId ? transcribeSeparatedStems : null}
          />
        </div>
      </div>
    </PageShell>
  );
}
