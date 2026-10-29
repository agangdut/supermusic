"use client";

import { useRef, useState } from "react";
import PrimaryButton from "./PrimaryButton";
import ThemedCard from "./ThemedCard";
import { LIBRARY_ACCEPT } from "./accept";

const fmtSize = (b) => (b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`);

export default function CsvCard({
  csvFiles,
  setCsvFiles,
  enrichCsv,
  busy,
}) {
  const inputRef = useRef();
  const [lookup, setLookup] = useState(true);
  const [limit, setLimit] = useState("500");
  const [dragging, setDragging] = useState(false);
  const [output, setOutput] = useState("combined");
  const files = csvFiles || [];

  // Picking again adds to the list (an account export is many files); same name = same file
  const add = (list) => {
    const picked = Array.from(list || []).filter((f) => /\.(csv|json|txt|tsv)$/i.test(f.name));
    if (!picked.length) return;
    setCsvFiles((prev) => {
      const byName = new Map((prev || []).map((f) => [f.name, f]));
      picked.forEach((f) => byName.set(f.name, f));
      return [...byName.values()];
    });
  };
  const remove = (name) => setCsvFiles((prev) => (prev || []).filter((f) => f.name !== name));
  const total = files.reduce((a, f) => a + f.size, 0);

  return (
    <ThemedCard
      title="CSV / library files"
      desc="Combine CSVs and Spotify or Apple Music exports into one clean track list, with duplicates merged and missing details filled in."
      footer={
        <>
          <div className="text-[11px] text-gray-400">
            {output === "separate" && files.length > 1
              ? `Output: ${files.length} enriched .csv files (+ a .zip)`
              : `Output: one enriched .csv${files.length > 1 ? ` from ${files.length} files` : ""}`}
          </div>

          <PrimaryButton
            onClick={() => enrichCsv({ lookup, limit: parseInt(limit, 10) || undefined, output: files.length > 1 ? output : "combined" })}
            disabled={!files.length || busy}
            className={(!files.length || busy) ? "opacity-50 cursor-not-allowed" : ""}
          >
            {files.length < 2 ? "Enrich" : output === "separate" ? `Enrich ${files.length} files` : `Combine & enrich ${files.length} files`}
          </PrimaryButton>
        </>
      }
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={LIBRARY_ACCEPT}
        onChange={(e) => { add(e.target.files); e.target.value = ""; }}
        className="hidden"
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); add(e.dataTransfer.files); }}
        className={`rounded-lg border border-dashed px-3 py-4 text-center text-xs transition-colors ${
          dragging ? "border-purple-400/70 bg-purple-500/10 text-white" : "border-white/15 text-gray-400 hover:border-purple-400/40 hover:text-gray-200"
        }`}
      >
        Drop files here or click to choose. Pick as many as you like.
      </button>

      {files.length > 0 && (
        <div className="rounded-lg border border-white/10 bg-black/20">
          <ul className="max-h-40 divide-y divide-white/5 overflow-y-auto text-xs">
            {files.map((f) => (
              <li key={f.name} className="flex items-center justify-between gap-2 px-2.5 py-1.5">
                <span className="min-w-0 truncate text-gray-200" title={f.name}>{f.name}</span>
                <span className="flex shrink-0 items-center gap-2 text-gray-500">
                  {fmtSize(f.size)}
                  <button onClick={() => remove(f.name)} className="hover:text-white" aria-label={`Remove ${f.name}`}>✕</button>
                </span>
              </li>
            ))}
          </ul>
          <div className="flex items-center justify-between border-t border-white/5 px-2.5 py-1.5 text-[11px] text-gray-500">
            <span>{files.length} file{files.length > 1 ? "s" : ""} · {fmtSize(total)}</span>
            <button onClick={() => setCsvFiles([])} className="hover:text-white">Clear</button>
          </div>
        </div>
      )}

      {files.length > 1 && (
        <div className="grid grid-cols-2 gap-2 text-xs" role="radiogroup" aria-label="Output">
          {[
            ["combined", "One combined file", "Duplicates merged, plays added up"],
            ["separate", "One file per input", `${files.length} enriched files, plus a .zip`],
          ].map(([id, label, hint]) => (
            <button key={id} type="button" role="radio" aria-checked={output === id} onClick={() => setOutput(id)}
              className={`rounded-lg border px-2.5 py-2 text-left transition-colors ${
                output === id ? "border-purple-400/60 bg-purple-500/10 text-white" : "border-white/10 text-gray-400 hover:border-white/20"
              }`}>
              <div className="font-medium">{label}</div>
              <div className="mt-0.5 text-[11px] text-gray-500">{hint}</div>
            </button>
          ))}
        </div>
      )}

      <label className="flex items-start gap-2 text-xs text-gray-300">
        <input type="checkbox" checked={lookup} onChange={(e) => setLookup(e.target.checked)} className="mt-0.5 accent-purple-500" />
        <span>
          Look up missing genre, year, tempo, key and energy online (MusicBrainz and Deezer; each song&apos;s 30-second
          preview is analysed on this computer). Songs looked up before are remembered.
        </span>
      </label>
      {lookup && (
        <label className="ml-5 flex items-center gap-2 text-xs text-gray-400">
          <span>Look up at most</span>
          <input
            type="number" min="1" max="50000" placeholder="500" value={limit}
            onChange={(e) => setLimit(e.target.value)}
            className="w-20 rounded border border-white/10 bg-black/30 px-2 py-0.5 text-xs text-white"
          />
          <span>songs, most-played first</span>
        </label>
      )}

      <p className="text-[11px] text-gray-500 leading-snug">
        Works with Exportify CSVs, Spotify&apos;s account data (StreamingHistory, Streaming_History_Audio, YourLibrary and
        Playlist JSON files), Apple Music exports, and any CSV with title and artist columns. The same song across files
        becomes one row with its plays added up.
      </p>
    </ThemedCard>
  );
}
