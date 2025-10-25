"use client";
import { useState } from "react";

function TabButton({ active, label, badge, onClick }) {
  return (
    <button
      onClick={onClick}
      className={
        "relative px-3 py-2 text-xs font-medium rounded-md border " +
        (active
          ? "bg-[#1e253d] border-white/20 text-white shadow-[0_10px_30px_rgba(168,85,247,0.4)]"
          : "bg-transparent border-white/10 text-gray-400 hover:text-white hover:border-white/20")
      }
    >
      <span className="flex items-center gap-2">
        <span>{label}</span>
        {badge ? (
          <span className="inline-block rounded-full bg-gradient-to-r from-purple-500 to-indigo-500 text-[10px] leading-none text-white px-1.5 py-0.5 shadow-[0_6px_18px_rgba(168,85,247,0.6)]">
            {badge}
          </span>
        ) : null}
      </span>
    </button>
  );
}

function EmptyState({ message }) {
  return (
    <div className="text-sm text-gray-500 text-center py-12">
      {message}
    </div>
  );
}

function MidiTab({ data }) {
  if (!data) {
    return <EmptyState message="No MIDI transcription yet." />;
  }

  return (
    <div className="text-sm text-gray-200 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <div className="font-medium text-white">Transcribed MIDI</div>
          <div className="text-[11px] text-gray-500">
            {data.filename || "midi_output.mid"}
          </div>
        </div>

        <a
          href={data.downloadUrl || "#"}
          download
          className="inline-flex items-center rounded-md px-3 py-2 text-xs font-medium
                     bg-gradient-to-r from-purple-500 to-indigo-500 text-white
                     shadow-[0_10px_30px_rgba(168,85,247,0.4)]
                     hover:shadow-[0_14px_40px_rgba(168,85,247,0.6)]
                     focus:outline-none focus:ring-2 focus:ring-purple-500/40"
        >
          Download MIDI
        </a>
      </div>

      {data.summary && (
        <div className="rounded-md border border-white/10 bg-[#0f172a] p-3 text-xs text-gray-300">
          <div className="text-gray-400 mb-1 font-medium">Details</div>
          <pre className="whitespace-pre-wrap break-all text-[11px] leading-relaxed">
            {data.summary}
          </pre>
        </div>
      )}
    </div>
  );
}

function StemsTab({ data }) {
  if (!data) {
    return <EmptyState message="No separated stems yet." />;
  }

  const stems = data.stems || [
    // You can remove this fallback once backend returns real stems.
    // { name: "vocals.wav", url: "#", size: "5.2 MB" },
    // { name: "drums.wav", url: "#", size: "4.7 MB" },
  ];

  if (!stems.length) {
    return <EmptyState message="No stems returned." />;
  }

  return (
    <div className="space-y-3 text-sm text-gray-200">
      {stems.map((stem, i) => (
        <div
          key={i}
          className="flex items-center justify-between flex-wrap gap-2 rounded-md border border-white/10 bg-[#1e253d] px-3 py-2"
        >
          <div>
            <div className="text-white text-sm font-medium leading-tight">
              {stem.name || `stem_${i + 1}.wav`}
            </div>
            <div className="text-[11px] text-gray-500 leading-tight">
              {stem.size || "audio stem"}
            </div>
          </div>

          <a
            href={stem.url || "#"}
            download
            className="inline-flex items-center rounded-md px-3 py-2 text-[11px] font-medium
                       bg-gradient-to-r from-purple-500 to-indigo-500 text-white
                       shadow-[0_10px_30px_rgba(168,85,247,0.4)]
                       hover:shadow-[0_14px_40px_rgba(168,85,247,0.6)]
                       focus:outline-none focus:ring-2 focus:ring-purple-500/40"
          >
            Download
          </a>
        </div>
      ))}
    </div>
  );
}

function CsvTab({ data }) {
  if (!data) {
    return <EmptyState message="No enriched CSV yet." />;
  }

  return (
    <div className="text-sm text-gray-200 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <div className="font-medium text-white">Enriched CSV</div>
          <div className="text-[11px] text-gray-500">
            {data.filename || "enriched_dataset.csv"}
          </div>
        </div>

        <a
          href={data.downloadUrl || "#"}
          download
          className="inline-flex items-center rounded-md px-3 py-2 text-xs font-medium
                     bg-gradient-to-r from-purple-500 to-indigo-500 text-white
                     shadow-[0_10px_30px_rgba(168,85,247,0.4)]
                     hover:shadow-[0_14px_40px_rgba(168,85,247,0.6)]
                     focus:outline-none focus:ring-2 focus:ring-purple-500/40"
        >
          Download CSV
        </a>
      </div>

      {Array.isArray(data.previewRows) && data.previewRows.length > 0 ? (
        <div className="overflow-x-auto rounded-md border border-white/10 bg-[#0f172a]">
          <table className="min-w-full text-left text-[11px] text-gray-300">
            <thead className="bg-black/20 text-[10px] uppercase tracking-wide text-gray-500">
              <tr>
                {Object.keys(data.previewRows[0]).map((col) => (
                  <th key={col} className="px-3 py-2 font-medium">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.previewRows.slice(0, 5).map((row, idx) => (
                <tr key={idx} className="border-t border-white/5">
                  {Object.keys(row).map((col) => (
                    <td key={col} className="px-3 py-2 text-gray-200">
                      {String(row[col])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-[11px] text-gray-500 italic">
          (No preview rows provided.)
        </div>
      )}
    </div>
  );
}

export default function ResultsConsole({ latestMidi, latestStems, latestCsv }) {
  // which tab is active
  const [tab, setTab] = useState("midi");

  // badges: show a little indicator when we actually have data
  const midiBadge = latestMidi ? "new" : null;
  const stemsBadge = latestStems ? "new" : null;
  const csvBadge = latestCsv ? "new" : null;

  return (
    <div className="rounded-lg border border-white/5 bg-black/20 max-h-[480px] overflow-y-auto text-sm p-4">
      {/* tabs row */}
      <div className="flex items-center gap-2 flex-wrap mb-4">
        <TabButton
          active={tab === "midi"}
          label="MIDI"
          badge={midiBadge}
          onClick={() => setTab("midi")}
        />
        <TabButton
          active={tab === "stems"}
          label="Stems"
          badge={stemsBadge}
          onClick={() => setTab("stems")}
        />
        <TabButton
          active={tab === "csv"}
          label="CSV"
          badge={csvBadge}
          onClick={() => setTab("csv")}
        />
      </div>

      {/* panel */}
      <div>
        {tab === "midi" && <MidiTab data={latestMidi} />}
        {tab === "stems" && <StemsTab data={latestStems} />}
        {tab === "csv" && <CsvTab data={latestCsv} />}
      </div>
    </div>
  );
}
