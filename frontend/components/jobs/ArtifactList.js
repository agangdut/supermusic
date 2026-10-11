"use client";
import React from "react";

/**
 * Artifacts can be:
 *  - an object map: { midi: "/path/file.mid", csv: "/path/out.csv" }
 *  - an array of { key, label, url }
 */
export default function ArtifactList({
  artifacts,
  onUse,            // optional: (key, url) => void
  className = "",
}) {
  if (!artifacts || (Array.isArray(artifacts) && artifacts.length === 0)) {
    return null;
  }

  const items = Array.isArray(artifacts)
    ? artifacts.map((a) => ({ key: a.key || a.label, label: a.label || a.key, url: a.url }))
    : Object.entries(artifacts).map(([key, url]) => ({ key, label: key, url }));

  const extEmoji = (label = "", url = "") => {
    const s = (url || label).toLowerCase();
    if (s.endsWith(".mid")) return "🎼";
    if (s.endsWith(".csv")) return "📄";
    if (s.endsWith(".wav") || s.endsWith(".mp3") || s.endsWith(".flac")) return "🎵";
    if (s.endsWith(".png") || s.endsWith(".jpg") || s.endsWith(".jpeg")) return "🖼️";
    return "📦";
    };

  const copy = async (text) => {
    try { await navigator.clipboard.writeText(text); } catch {}
  };

  return (
    <ul className={`mt-2 divide-y divide-white/5 rounded-lg border border-white/10 bg-black/20 ${className}`}>
      {items.map(({ key, label, url }) => (
        <li key={key} className="flex items-center justify-between gap-3 px-3 py-2">
          <div className="min-w-0 flex items-center gap-2">
            <span className="text-base">{extEmoji(label, url)}</span>
            <span className="truncate text-sm font-medium text-gray-200">{label}</span>
          </div>
          <div className="shrink-0 flex items-center gap-2">
            {url && (
              <>
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm text-indigo-300 underline decoration-dotted hover:decoration-solid"
                >
                  open
                </a>
                <button
                  onClick={() => copy(url)}
                  className="rounded-md border border-white/10 px-2 py-1 text-xs text-gray-300 hover:bg-white/10"
                  title="Copy URL"
                >
                  copy
                </button>
              </>
            )}
            {onUse && url && (
              <button
                onClick={() => onUse(key, url)}
                className="rounded-md border border-white/10 px-2 py-1 text-xs text-gray-300 hover:bg-white/10"
              >
                use
              </button>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
