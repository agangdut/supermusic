"use client";

import { useState } from "react";
import PrimaryButton from "./PrimaryButton";
import ThemedCard from "./ThemedCard";

export default function AudioCard({
  audioFile,
  setAudioFile,
  transcribeMidi,
  separateStems,
  busy,
}) {
  const [model, setModel] = useState("auto");
  return (
    <ThemedCard
      title="Audio"
      desc="Upload audio once, then run transcription (MIDI) or stem separation."
      footer={
        <>
          <div className="text-[11px] text-gray-400">
            Accepted: mp3 / wav / flac
          </div>
          <div className="flex gap-2 flex-wrap">
            <PrimaryButton
              onClick={() => transcribeMidi(model)}
              disabled={!audioFile || busy}
            >
              Transcribe → MIDI
            </PrimaryButton>
            <PrimaryButton
              onClick={separateStems}
              disabled={!audioFile || busy}
            >
              Separate Stems
            </PrimaryButton>
          </div>
        </>
      }
    >
      <label className="text-sm font-medium text-gray-300">Audio file</label>
      <input
        type="file"
        accept="audio/*"
        onChange={(e) => setAudioFile(e.target.files?.[0] || null)}
        className="text-gray-300 text-xs file:rounded-md file:border file:border-white/10
                   file:bg-[#1e253d] file:px-2 file:py-1 file:text-gray-100
                   hover:file:border-purple-500/40
                   file:text-xs file:transition-colors"
      />

      <div className="mt-4">
        <span className="text-sm font-medium text-gray-300">MIDI model</span>
        <div className="mt-2 grid grid-cols-2 gap-2">
          {[
            { id: "auto", name: "Auto", note: "Detects the instruments and picks for you" },
            { id: "stems", name: "Stems", note: "Full band: one MIDI track per instrument" },
            { id: "piano", name: "Piano", note: "Solo piano, trained on MAESTRO" },
            { id: "basic", name: "General", note: "Fastest, any single instrument" },
          ].map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => setModel(m.id)}
              className={`rounded-lg border px-3 py-2 text-left transition ${
                model === m.id
                  ? "border-purple-400/60 bg-purple-500/10 text-white"
                  : "border-white/10 text-gray-400 hover:border-white/20"
              }`}
            >
              <span className="block text-xs font-semibold">{m.name}</span>
              <span className="block text-[11px] text-gray-500">{m.note}</span>
            </button>
          ))}
        </div>
      </div>
    </ThemedCard>
  );
}
