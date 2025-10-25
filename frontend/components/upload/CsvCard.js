"use client";

import PrimaryButton from "./PrimaryButton";
import ThemedCard from "./ThemedCard";

export default function CsvCard({
  csvFile,
  setCsvFile,
  enrichCsv,
  busy,
}) {
  return (
    <ThemedCard
      title="CSV"
      desc="Upload a CSV of tracks and enrich it with metadata (key, BPM, tags, etc.)."
      footer={
        <>
          <div className="text-[11px] text-gray-400">
            Output: enriched .csv
          </div>

          <PrimaryButton
            onClick={enrichCsv}
            disabled={!csvFile || busy}
            className={
              (!csvFile || busy)
                ? "opacity-50 cursor-not-allowed"
                : ""
            }
          >
            Enrich CSV
          </PrimaryButton>
        </>
      }
    >
      <label className="text-sm font-medium text-gray-300">
        CSV file
      </label>

      <input
        type="file"
        accept=".csv"
        onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
        className="text-gray-300 text-xs file:mr-2 file:rounded-md file:border file:border-white/10
                   file:bg-[#1e253d] file:px-2 file:py-1 file:text-gray-100
                   hover:file:border-purple-500/40 hover:file:text-white
                   file:text-xs file:transition-colors"
      />

      <p className="text-[11px] text-gray-500 leading-snug">
        Include columns like title / artist / album. We’ll infer genre, BPM, key, etc.
      </p>
    </ThemedCard>
  );
}
