"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

import PageShell from "@/components/layout/PageShell";
import { takeCsvForStudio } from "@/lib/handoff";
import useUploadJobs from "@/hooks/useUploadJobs";

import ToastBanner from "@/components/upload/ToastBanner";
import AudioCard from "@/components/upload/AudioCard";
import CsvCard from "@/components/upload/CsvCard";
import { LastfmCard } from "@/components/upload/LastfmImport";
import StatusCard from "@/components/upload/StatusCard";
import ResultsCard from "@/components/upload/ResultsCard"; // wraps ThemedCard+ResultsConsole

export default function UploadPage() {
  const {
    audioFile,
    csvFiles,
    jobs,
    toast,
    busy,
    runningCount,
    latestMidi,
    latestStems,
    latestStemsJobId,
    latestCsv,
    setAudioFile,
    setCsvFiles,
    transcribeMidi,
    transcribeSeparatedStems,
    separateStems,
    enrichCsv,
    importFromLastfm,
    clearJobs,
    retryJob,
  } = useUploadJobs();

  // A running Last.fm import: say what's happening and where to go meanwhile
  const lastfmJob = jobs.find((j) => j.payload?.source === "lastfm" && ["running", "queued"].includes(j.status));

  // Sent here from the map with a CSV that needs enriching: put it in the CSV card
  const router = useRouter();
  useEffect(() => {
    if (router.query.enrich == null) return;
    const files = takeCsvForStudio();
    if (files?.length) {
      setCsvFiles(files);
      setTimeout(() => document.getElementById("csv-card")?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
    }
    router.replace("/upload", undefined, { shallow: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.query.enrich]);

  // Sent here from the map with a Last.fm username: start the import here, so it can be watched
  const startedRef = useRef(null);
  const lastfmUser = typeof router.query.lastfm === "string" ? router.query.lastfm : "";
  useEffect(() => {
    if (!lastfmUser || startedRef.current === lastfmUser) return;
    startedRef.current = lastfmUser;
    importFromLastfm(lastfmUser);
    router.replace("/upload", undefined, { shallow: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastfmUser]);

  return (
    <PageShell>
      <ToastBanner toast={toast} />

      {lastfmJob && <LastfmWaiting job={lastfmJob} />}

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
          <LastfmCard onImport={importFromLastfm} busy={busy || !!lastfmJob} initialUser={lastfmUser} />

          <AudioCard
            audioFile={audioFile}
            setAudioFile={setAudioFile}
            transcribeMidi={transcribeMidi}
            separateStems={separateStems}
            busy={busy}
          />

          <div id="csv-card" className="scroll-mt-24">
          <CsvCard
            csvFiles={csvFiles}
            setCsvFiles={setCsvFiles}
            enrichCsv={enrichCsv}
            busy={busy}
          />
          </div>

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

// Shown while a Last.fm import runs: what's going on, and that it's fine to look around
function LastfmWaiting({ job }) {
  const pct = Math.max(2, Math.min(100, job.progress || 0));
  const places = [
    ["/maps", "Explore", "other people's maps"],
    ["/atlas", "Atlas", "everyone's music in one galaxy"],
    ["/play", "Play", "the music quiz"],
    ["/artists", "Artists", "artist pages"],
  ];
  return (
    <div className="mb-6 rounded-2xl border border-fuchsia-400/25 bg-gradient-to-br from-fuchsia-500/[0.08] to-indigo-500/[0.08] p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-white">
        <span className="h-2 w-2 animate-pulse rounded-full bg-fuchsia-400" />
        Enriching {job.payload?.username}&apos;s Last.fm library
      </div>
      <p className="mt-1 max-w-prose text-xs leading-5 text-gray-300">
        We read your scrobbles from Last.fm, and now each song is being looked up for its genre, year, tempo, key and energy.
        That&apos;s what lets the map group your songs into galaxies. Big libraries take a while; this page shows each step,
        and the result appears on the right with a button to open your map.
      </p>
      <div className="mt-3 h-1.5 w-full rounded-full bg-white/10">
        <div className="h-1.5 rounded-full bg-gradient-to-r from-fuchsia-500 to-indigo-500 transition-all" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1 text-[11px] text-gray-400">{job.message}</div>
      <div className="mt-3 text-xs text-gray-400">
        It keeps running while you look around. Come back to the Studio to see it finish:
        <div className="mt-2 flex flex-wrap gap-2">
          {places.map(([href, label, hint]) => (
            <Link key={href} href={href} className="rounded-lg border border-white/10 bg-black/20 px-2.5 py-1.5 text-gray-200 hover:bg-white/10">
              <b className="text-white">{label}</b> <span className="text-gray-500">· {hint}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
