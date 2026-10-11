"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import StemsToMidi from "./StemsToMidi";

// Players use the Web Audio API, so they only load in the browser
const MidiPlayer = dynamic(() => import("@/components/player/MidiPlayer"), { ssr: false });
const StemMixer = dynamic(() => import("@/components/player/StemMixer"), { ssr: false });

const fileName = (url) => decodeURIComponent(String(url).split("/").pop() || "").replace(/^[0-9a-f-]{36}_/, "");

export default function ResultsConsole({ latestMidi, latestStems, latestCsv, onStemsToMidi, busy }) {
  const [tab, setTab] = useState("midi");

  // Jump to whichever result arrived most recently
  useEffect(() => { if (latestMidi) setTab("midi"); }, [latestMidi]);
  useEffect(() => { if (latestStems) setTab("stems"); }, [latestStems]);

  const midi = typeof latestMidi === "string" ? { midi: latestMidi } : latestMidi;
  const tabs = [
    { key: "midi", label: "MIDI", ready: !!midi?.midi },
    { key: "stems", label: "Stems", ready: !!latestStems },
    { key: "csv", label: "CSV", ready: !!latestCsv },
  ];

  return (
    <div className="flex flex-col rounded-lg border border-white/10 bg-[#0f172a]">
      <div className="flex border-b border-white/10">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex-1 py-2 text-sm font-medium transition-colors ${
              tab === t.key ? "bg-[#1e293b] text-white" : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {t.label}
            {t.ready && <span className="ml-1.5 inline-block h-1.5 w-1.5 rounded-full bg-emerald-400 align-middle" />}
          </button>
        ))}
      </div>

      <div className="min-h-[200px] p-4">
        {tab === "midi" && (midi?.midi ? (
          <div className="space-y-4">
            <MidiPlayer url={midi.midi} title={fileName(midi.midi)} />
            {midi.preview && (
              <div>
                <div className="mb-1 text-[11px] uppercase tracking-wider text-gray-500">Rendered piano preview</div>
                <audio controls src={midi.preview} className="w-full" />
              </div>
            )}
            {midi.midi_original && (
              <a href={midi.midi_original} download className="text-xs text-indigo-300 hover:underline">
                Download the original transcription (before two-hand arranging)
              </a>
            )}
          </div>
        ) : <Empty what="MIDI" />)}

        {tab === "stems" && (latestStems ? (
          <div className="space-y-4">
            <StemMixer stems={latestStems} />
            {onStemsToMidi && <StemsToMidi stems={latestStems} onConvert={onStemsToMidi} busy={busy} />}
          </div>
        ) : <Empty what="stem" />)}

        {tab === "csv" && (latestCsv ? (
          <a href={latestCsv} target="_blank" rel="noopener noreferrer" className="text-sm text-indigo-400 underline hover:text-indigo-300">
            Download the enriched CSV
          </a>
        ) : <Empty what="CSV" />)}
      </div>
    </div>
  );
}

function Empty({ what }) {
  return <div className="py-8 text-center text-sm text-gray-400">No {what} results yet.</div>;
}
