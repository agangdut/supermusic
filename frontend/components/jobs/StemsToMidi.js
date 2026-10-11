"use client";

// After a separation: tick the stems you want and turn just those into MIDI.
// Reuses the separated files, so Demucs doesn't run again.
import { useEffect, useState } from "react";

const HINTS = {
  vocals: "the sung melody",
  bass: "the bass line",
  piano: "piano / keys",
  guitar: "guitar parts",
  drums: "kick, snare, hi-hat",
  other: "synths, strings, the rest",
};

export default function StemsToMidi({ stems, onConvert, busy }) {
  const names = Object.keys(stems || {}).filter((k) => typeof stems[k] === "string" && /\.(wav|mp3|flac|ogg)$/i.test(stems[k]));
  const [picked, setPicked] = useState([]);
  const [playable, setPlayable] = useState(false);

  // Start with the melody and bass picked: they're usually what people want from pop
  useEffect(() => {
    const start = names.filter((n) => n === "vocals" || n === "bass");
    setPicked(start.length ? start : names.slice(0, 1));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [names.join("|")]);

  if (!names.length) return null;
  const toggle = (n) => setPicked((p) => (p.includes(n) ? p.filter((x) => x !== n) : [...p, n]));

  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
      <div className="text-sm font-medium text-gray-200">Turn stems into MIDI</div>
      <div className="mb-2 text-[11px] text-gray-500">
        Pick only the parts you want. Each one gets its own track, and the rest of the song can&apos;t leak into it.
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {names.map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => toggle(n)}
            className={`rounded-lg border px-3 py-1.5 text-left transition ${
              picked.includes(n)
                ? "border-purple-400/60 bg-purple-500/10 text-white"
                : "border-white/10 text-gray-400 hover:border-white/20"
            }`}
          >
            <span className="block text-xs font-semibold capitalize">{n}</span>
            <span className="block text-[11px] text-gray-500">{HINTS[n] || ""}</span>
          </button>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <label className="flex items-center gap-2 text-[11px] text-gray-400 cursor-pointer">
          <input type="checkbox" checked={playable} onChange={(e) => setPlayable(e.target.checked)} className="accent-purple-500" />
          Playable by two hands
        </label>
        <button
          type="button"
          disabled={busy || !picked.length}
          onClick={() => onConvert(picked, { playable })}
          className="rounded-md bg-gradient-to-r from-fuchsia-500 to-indigo-500 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
        >
          Make MIDI from {picked.length || "no"} stem{picked.length === 1 ? "" : "s"}
        </button>
      </div>
    </div>
  );
}
