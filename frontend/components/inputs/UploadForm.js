"use client";
import React, { useRef, useState } from "react";
import Button from "./Button";
import Select from "./Select";
import TextField from "./TextField";

/**
 * Consolidated UploadForm with four actions:
 *  - Convert to MIDI
 *  - Enrich CSV
 *  - Separate Stems
 *  - Download by URL
 *
 * Callbacks receive File objects (when selected) or strings.
 * You handle uploading/POSTing in the parent using these values.
 */
export default function UploadForm({
  onSubmitMidi,       // (fileOrPath, { model, onset_sensitivity })
  onSubmitCsv,        // (fileOrPath, { strategy })
  onSubmitStems,      // (fileOrPath, { model, stems })
  onSubmitDownload,   // (url)
}) {
  // MIDI
  const midiRef = useRef(null);
  const [midiModel, setMidiModel] = useState("basic");
  const [sensitivity, setSensitivity] = useState(0.6);

  // CSV
  const csvRef = useRef(null);
  const [strategy, setStrategy] = useState("youtube+acousticbrainz");

  // Stems
  const stemsRef = useRef(null);
  const [stemsModel, setStemsModel] = useState("htdemucs");
  const [stems, setStems] = useState(["vocals", "drums", "bass", "other"]);
  const toggleStem = (s) =>
    setStems((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));

  // Download
  const [url, setUrl] = useState("");

  // helpers
  const getFile = (ref) => ref.current?.files?.[0] || null;

  return (
    <div className="grid gap-6">
      {/* MIDI */}
      <section className="rounded-xl border bg-white p-4">
        <h3 className="text-base font-semibold mb-3">🎹 Convert audio to MIDI</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="block text-sm font-medium mb-1">Audio file</label>
            <input ref={midiRef} type="file" accept=".wav,.mp3,.flac,.m4a" className="block w-full text-sm" />
          </div>
          <Select
            label="Model"
            value={midiModel}
            onChange={(e) => setMidiModel(e.target.value)}
            options={[
              { value: "basic", label: "Basic (fast)" },
              { value: "melody", label: "Melody (mono)" },
              { value: "poly", label: "Polyphonic (slower)" },
            ]}
          />
          <div className="sm:col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Onset sensitivity ({sensitivity})
            </label>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={sensitivity}
              onChange={(e) => setSensitivity(parseFloat(e.target.value))}
              className="w-full"
            />
          </div>
        </div>
        <div className="mt-3">
          <Button
            onClick={() => {
              const file = getFile(midiRef);
              if (!file) return alert("Pick an audio file first.");
              onSubmitMidi?.(file, { model: midiModel, onset_sensitivity: sensitivity });
            }}
          >
            Convert to MIDI
          </Button>
        </div>
      </section>

      {/* CSV */}
      <section className="rounded-xl border bg-white p-4">
        <h3 className="text-base font-semibold mb-3">🧩 Enrich CSV metadata</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="block text-sm font-medium mb-1">CSV file</label>
            <input ref={csvRef} type="file" accept=".csv" className="block w-full text-sm" />
          </div>
          <Select
            label="Strategy"
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            options={[
              { value: "youtube+acousticbrainz", label: "YouTube + AcousticBrainz" },
              { value: "musicbrainz", label: "MusicBrainz only" },
              { value: "local", label: "Local heuristics" },
            ]}
          />
        </div>
        <div className="mt-3">
          <Button
            variant="secondary"
            onClick={() => {
              const file = getFile(csvRef);
              if (!file) return alert("Pick a CSV file first.");
              onSubmitCsv?.(file, { strategy });
            }}
          >
            Enrich CSV
          </Button>
        </div>
      </section>

      {/* Stems */}
      <section className="rounded-xl border bg-white p-4">
        <h3 className="text-base font-semibold mb-3">🥁 Separate audio into stems</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="block text-sm font-medium mb-1">Audio file</label>
            <input ref={stemsRef} type="file" accept=".wav,.mp3,.flac,.m4a" className="block w-full text-sm" />
          </div>
          <Select
            label="Model"
            value={stemsModel}
            onChange={(e) => setStemsModel(e.target.value)}
            options={[
              { value: "htdemucs", label: "HTDemucs" },
              { value: "mdx", label: "MDX" },
            ]}
          />
        </div>
        <fieldset className="mt-2">
          <legend className="text-sm font-medium text-gray-700 mb-1">Stems</legend>
          <div className="flex flex-wrap gap-3">
            {["vocals", "drums", "bass", "other"].map((s) => (
              <label key={s} className="inline-flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={stems.includes(s)}
                  onChange={() => toggleStem(s)}
                  className="rounded"
                />
                {s}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="mt-3">
          <Button
            variant="secondary"
            onClick={() => {
              const file = getFile(stemsRef);
              if (!file) return alert("Pick an audio file first.");
              onSubmitStems?.(file, { model: stemsModel, stems });
            }}
          >
            Separate Stems
          </Button>
        </div>
      </section>

      {/* Download */}
      <section className="rounded-xl border bg-white p-4">
        <h3 className="text-base font-semibold mb-3">⬇️ Download by URL</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField
            label="Media URL"
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://youtube.com/watch?v=..."
            required
            helperText="Paste a public media URL"
          />
        </div>
        <div className="mt-3">
          <Button
            variant="ghost"
            onClick={() => {
              if (!url.trim()) return alert("Paste a URL first.");
              onSubmitDownload?.(url.trim());
            }}
          >
            Download
          </Button>
        </div>
      </section>
    </div>
  );
}
