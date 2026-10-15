"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import StemsToMidi from "./StemsToMidi";
import { toArtifactUrl } from "@/lib/api";

// Players use the Web Audio API, so they only load in the browser
const MidiPlayer = dynamic(() => import("@/components/player/MidiPlayer"), { ssr: false });
const StemMixer = dynamic(() => import("@/components/player/StemMixer"), { ssr: false });

const fileName = (url) => decodeURIComponent(String(url).split("/").pop() || "").replace(/^[0-9a-f-]{36}_/, "");

export default function ResultsConsole({ latestMidi, latestStems, latestCsv, onStemsToMidi, busy }) {
  const [tab, setTab] = useState("midi");

  // Jump to whichever result arrived most recently
  useEffect(() => { if (latestMidi) setTab("midi"); }, [latestMidi]);
  useEffect(() => { if (latestStems) setTab("stems"); }, [latestStems]);
  useEffect(() => { if (latestCsv) setTab("csv"); }, [latestCsv]);

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
            {midi.melody && !midi.melody.error && <MelodyScore m={midi.melody} />}
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

        {tab === "csv" && (latestCsv ? <CsvSummary csv={latestCsv} /> : <Empty what="CSV" />)}
      </div>
    </div>
  );
}

const FIELD_LABELS = {
  genre: "Genre", year: "Year", bpm: "Tempo", key: "Key", energy: "Energy",
  play_count: "Play count", first_played: "Play dates", liked: "Liked", playlists: "Playlists",
};

// What the merge and lookup did, with links to the file and the Music Map
function CsvSummary({ csv }) {
  const c = typeof csv === "string" ? { url: csv } : csv; // older saved results were just a link
  const m = c.metrics;
  const before = m?.coverage_before || {};
  const after = m?.coverage_after || {};
  return (
    <div className="space-y-4 text-sm">
      {m && (
        <>
          <div className="grid grid-cols-3 gap-2">
            <Stat value={m.songs?.toLocaleString()} label={m.outputs ? "different songs" : "songs"} />
            <Stat value={m.files?.length} label={m.files?.length === 1 ? "file" : "files"} />
            {m.outputs
              ? <Stat value={m.outputs.filter((o) => o.csv).length} label="enriched files" />
              : <Stat value={m.duplicates_merged?.toLocaleString()} label="duplicates merged" />}
          </div>
          {m.files?.length > 0 && (
            <ul className="space-y-1 text-xs">
              {m.files.map((f) => (
                <li key={f.file} className="flex justify-between gap-3 text-gray-400">
                  <span className="min-w-0 truncate text-gray-200" title={f.file}>{f.file}</span>
                  <span className="shrink-0">{f.type} · {f.songs.toLocaleString()} songs</span>
                </li>
              ))}
            </ul>
          )}
          {Object.keys(after).length > 0 && (
            <div>
              <div className="mb-1.5 text-[11px] uppercase tracking-wider text-gray-500">Songs with each detail</div>
              <div className="space-y-1">
                {Object.keys(after).map((k) => (
                  <div key={k} className="flex items-center gap-2 text-xs">
                    <span className="w-20 shrink-0 text-gray-400">{FIELD_LABELS[k] || k}</span>
                    <div className="relative h-1.5 flex-1 rounded-full bg-white/5">
                      <div className="absolute h-1.5 rounded-full bg-indigo-400/80" style={{ width: `${after[k] * 100}%` }} />
                      <div className="absolute h-1.5 rounded-full bg-gray-500" style={{ width: `${(before[k] || 0) * 100}%` }} />
                    </div>
                    <span className="w-24 shrink-0 text-right tabular-nums text-gray-400">
                      {before[k] != null && Math.round(before[k] * 100) !== Math.round(after[k] * 100)
                        ? `${Math.round(before[k] * 100)}% → ${Math.round(after[k] * 100)}%`
                        : `${Math.round(after[k] * 100)}%`}
                    </span>
                  </div>
                ))}
              </div>
              {m.matched_online != null && (
                <p className="mt-1.5 text-[11px] text-gray-500">{m.matched_online.toLocaleString()} songs found online. Grey = before, blue = added.</p>
              )}
            </div>
          )}
        </>
      )}
      {m?.outputs?.length > 0 && (
        <div>
          <div className="mb-1.5 text-[11px] uppercase tracking-wider text-gray-500">Enriched files</div>
          <ul className="space-y-1 text-xs">
            {m.outputs.map((o) => (
              <li key={o.file} className="flex items-center justify-between gap-3">
                <span className="min-w-0 truncate text-gray-200" title={o.file}>{o.file}</span>
                <span className="flex shrink-0 items-center gap-3 text-gray-400">
                  {o.songs.toLocaleString()} songs
                  {o.csv ? (
                    <>
                      <a href={toArtifactUrl(o.csv)} target="_blank" rel="noopener noreferrer" className="text-indigo-400 underline hover:text-indigo-300">Download</a>
                      <a href={`/?csv=${encodeURIComponent(o.csv)}`} className="text-fuchsia-300 underline hover:text-fuchsia-200">Map</a>
                    </>
                  ) : <span className="text-gray-500">no songs</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        {c.zip && (
          <a href={c.zip} className="text-indigo-400 underline hover:text-indigo-300">Download all as .zip</a>
        )}
        {c.url && (
          <a href={c.url} target="_blank" rel="noopener noreferrer" className="text-indigo-400 underline hover:text-indigo-300">
            Download the enriched CSV
          </a>
        )}
        {c.library_csv && !m?.outputs && (
          <a href={`/?csv=${encodeURIComponent(c.library_csv)}`} className="text-fuchsia-300 underline hover:text-fuchsia-200">
            Open it in the Music Map
          </a>
        )}
      </div>
    </div>
  );
}

function Stat({ value, label }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2">
      <div className="text-lg font-semibold tabular-nums text-white">{value ?? "–"}</div>
      <div className="text-[11px] text-gray-500">{label}</div>
    </div>
  );
}

function Empty({ what }) {
  return <div className="py-8 text-center text-sm text-gray-400">No {what} results yet.</div>;
}

// How closely the MIDI melody follows the singer's own pitch
function MelodyScore({ m }) {
  const tone = m.melody_match >= 60 ? "text-emerald-300" : m.melody_match >= 35 ? "text-amber-300" : "text-rose-300";
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
      <div className="flex items-baseline gap-2">
        <span className={`text-2xl font-bold tabular-nums ${tone}`}>{Math.round(m.melody_match)}%</span>
        <span className="text-sm text-gray-300">melody match</span>
      </div>
      <div className="mt-1 text-[11px] text-gray-500">
        Of the {Math.round(m.sung_seconds)} s the singer is singing, the MIDI plays the same note {Math.round(m.melody_match)}% of the time
        ({Math.round(m.octave_ok)}% if a wrong octave is forgiven). It plays something {Math.round(m.coverage)}% of the time,
        and {Math.round(m.extra)}% of its melody notes land where nobody is singing.
      </div>
    </div>
  );
}
