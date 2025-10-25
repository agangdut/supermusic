"use client";
import { useState, useRef } from "react";

/**
 * Sticky, responsive toolbar for quick actions.
 * Props (all optional, provide the ones you use):
 *  - onOpenLibrary: () => void
 *  - onRequestMidi: (fileOrPath?: string|File) => void
 *  - onRequestCsv: (fileOrPath?: string|File) => void
 *  - onRequestStems: (fileOrPath?: string|File) => void
 *  - onRequestDownload: (url: string) => void
 */
export default function Toolbar({
  onOpenLibrary,
  onRequestMidi,
  onRequestCsv,
  onRequestStems,
  onRequestDownload,
}) {
  const [downloadURL, setDownloadURL] = useState("");
  const fileMidiRef = useRef(null);
  const fileCsvRef = useRef(null);
  const fileStemsRef = useRef(null);

  return (
    <div className="sticky top-14 z-30 bg-white/80 backdrop-blur border-b">
      <div className="mx-auto max-w-6xl px-4 py-2 flex flex-wrap items-center gap-2">
        {/* Library */}
        <button
          onClick={onOpenLibrary}
          className="rounded-lg border px-3 py-1.5 text-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          📚 Library
        </button>

        <div className="h-6 w-px bg-gray-200 mx-1" />

        {/* MIDI */}
        <input
          ref={fileMidiRef}
          type="file"
          accept=".wav,.mp3,.flac,.m4a"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onRequestMidi?.(f);
            e.target.value = "";
          }}
        />
        <button
          onClick={() => fileMidiRef.current?.click()}
          className="rounded-lg border px-3 py-1.5 text-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
          title="Convert audio to MIDI"
        >
          🎹 Convert MIDI
        </button>

        {/* CSV */}
        <input
          ref={fileCsvRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onRequestCsv?.(f);
            e.target.value = "";
          }}
        />
        <button
          onClick={() => fileCsvRef.current?.click()}
          className="rounded-lg border px-3 py-1.5 text-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
          title="Enrich CSV metadata"
        >
          🧩 Enrich CSV
        </button>

        {/* Stems */}
        <input
          ref={fileStemsRef}
          type="file"
          accept=".wav,.mp3,.flac,.m4a"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onRequestStems?.(f);
            e.target.value = "";
          }}
        />
        <button
          onClick={() => fileStemsRef.current?.click()}
          className="rounded-lg border px-3 py-1.5 text-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
          title="Separate audio into stems"
        >
          🥁 Separate Stems
        </button>

        <div className="h-6 w-px bg-gray-200 mx-1" />

        {/* Download by URL */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (downloadURL.trim()) onRequestDownload?.(downloadURL.trim());
          }}
          className="flex items-center gap-2"
        >
          <input
            value={downloadURL}
            onChange={(e) => setDownloadURL(e.target.value)}
            placeholder="Paste media URL…"
            className="w-56 rounded-lg border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="submit"
            className="rounded-lg border px-3 py-1.5 text-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            ⬇️ Download
          </button>
        </form>
      </div>
    </div>
  );
}
