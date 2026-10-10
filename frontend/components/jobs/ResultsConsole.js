"use client";

import { useState } from "react";

export default function ResultsConsole({ latestMidi, latestStems, latestCsv }) {
  const [tab, setTab] = useState("midi");

  const tabs = [
    { key: "midi", label: "MIDI" },
    { key: "stems", label: "Stems" },
    { key: "csv", label: "CSV" },
  ];

  const activeData =
    tab === "midi" ? latestMidi : tab === "stems" ? latestStems : latestCsv;

  return (
    <div className="flex flex-col bg-[#0f172a] border border-white/10 rounded-lg">
      {/* Tab headers */}
      <div className="flex border-b border-white/10">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex-1 text-sm font-medium py-2 transition-colors ${
              tab === t.key
                ? "text-white bg-[#1e293b]"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="p-4 min-h-[200px]">
        {!activeData ? (
          <div className="text-gray-400 text-sm py-8 text-center">
            No {tab.toUpperCase()} results yet.
          </div>
        ) : typeof activeData === "object" && !activeData.startsWith("http") ? (
          // If it's an object (like stems dict), show as JSON
          <pre className="text-xs bg-[#0f172a]/80 text-gray-200 rounded-lg border border-white/10 p-3 overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(activeData, null, 2)}
          </pre>
        ) : (
          // If it's a URL string or object with URL-like value
          <div className="p-4 space-y-2">
            {typeof activeData === "object" ? (
              // Handle object with multiple artifacts (like stems)
              Object.entries(activeData).map(([key, url]) => (
                <div key={key} className="flex items-center justify-between">
                  <span className="text-sm text-gray-300 capitalize">{key}</span>
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-indigo-400 hover:text-indigo-300 underline"
                  >
                    Download
                  </a>
                </div>
              ))
            ) : (
              // Single URL string
              <a
                href={activeData}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-indigo-400 hover:text-indigo-300 underline"
              >
                Download {tab.toUpperCase()} file
              </a>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
