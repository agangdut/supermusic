"use client";

import { useState } from "react";
import PrimaryButton from "./PrimaryButton";
import ThemedCard from "./ThemedCard";

// The six parts the Stems model splits a song into
const STEMS = [
  { id: "vocals", name: "Vocals" },
  { id: "bass", name: "Bass" },
  { id: "piano", name: "Piano" },
  { id: "guitar", name: "Guitar" },
  { id: "drums", name: "Drums" },
  { id: "other", name: "Other" },
];

export default function AudioCard({
  audioFile,
  setAudioFile,
  transcribeMidi,
  separateStems,
  busy,
}) {
  const [model, setModel] = useState("auto");
  const [playable, setPlayable] = useState(false);
  const [vocalTrack, setVocalTrack] = useState(true);
  const [handSpan, setHandSpan] = useState(14);
  const [stems, setStems] = useState(STEMS.map((s) => s.id));
  const toggleStem = (id) => setStems((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
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
              onClick={() => transcribeMidi(model, {
                playable, handSpan, vocalTrack,
                stems: stems.length === STEMS.length ? undefined : stems,
              })}
              disabled={!audioFile || busy || (model === "stems" && !stems.length)}
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
            { id: "muscriptor", name: "Full band", note: "Most accurate on pop and band mixes (MuScriptor, uses your GPU)" },
            { id: "multi", name: "Full band (YourMT3+)", note: "Older full-band model: about 3x faster, less accurate on pop" },
            { id: "stems", name: "Stems", note: "Split first, then one track per instrument" },
            { id: "piano", name: "Piano", note: "Solo piano, trained on MAESTRO" },
            { id: "basic", name: "General", note: "Fastest, any single instrument" },
            { id: "cover", name: "Piano cover", note: "Arranges the song for piano (Pop2Piano)" },
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

      {model === "stems" && (
        <div className="mt-4">
          <span className="text-sm font-medium text-gray-300">Which parts to turn into MIDI</span>
          <span className="block text-[11px] text-gray-500">
            Untick what you don&apos;t need. Just Vocals + Bass often gives the cleanest result on pop.
          </span>
          <div className="mt-2 grid grid-cols-3 gap-2">
            {STEMS.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => toggleStem(s.id)}
                className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
                  stems.includes(s.id)
                    ? "border-purple-400/60 bg-purple-500/10 text-white"
                    : "border-white/10 text-gray-500 hover:border-white/20"
                }`}
              >
                {s.name}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4">
        <label className="flex items-start gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={vocalTrack}
            onChange={(e) => setVocalTrack(e.target.checked)}
            className="mt-0.5 accent-purple-500"
          />
          <span>
            <span className="block text-sm font-medium text-gray-300">Voice as its own melody</span>
            <span className="block text-[11px] text-gray-500">
              Puts the singer on a clean "Lead vocal" track, one note at a time. With General, the voice is
              separated first so it can&apos;t become instrument notes (adds about a minute).
            </span>
          </span>
        </label>
      </div>

      <div className="mt-4">
        <label className="flex items-start gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={playable}
            onChange={(e) => setPlayable(e.target.checked)}
            className="mt-0.5 accent-purple-500"
          />
          <span>
            <span className="block text-sm font-medium text-gray-300">Playable by two hands</span>
            <span className="block text-[11px] text-gray-500">
              Splits into left and right hand, at most 5 notes each, within one stretch
            </span>
          </span>
        </label>
        {playable && (
          <div className="mt-2 grid grid-cols-3 gap-2">
            {[
              { span: 12, name: "Small", note: "Octave" },
              { span: 14, name: "Medium", note: "Ninth" },
              { span: 16, name: "Large", note: "Tenth" },
            ].map((h) => (
              <button
                key={h.span}
                type="button"
                onClick={() => setHandSpan(h.span)}
                className={`rounded-lg border px-3 py-2 text-left transition ${
                  handSpan === h.span
                    ? "border-purple-400/60 bg-purple-500/10 text-white"
                    : "border-white/10 text-gray-400 hover:border-white/20"
                }`}
              >
                <span className="block text-xs font-semibold">{h.name} hands</span>
                <span className="block text-[11px] text-gray-500">{h.note}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </ThemedCard>
  );
}
