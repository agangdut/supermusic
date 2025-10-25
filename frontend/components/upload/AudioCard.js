"use client";

import PrimaryButton from "./PrimaryButton";
import ThemedCard from "./ThemedCard";

export default function AudioCard({
  audioFile,
  setAudioFile,
  transcribeMidi,
  separateStems,
  busy,
}) {
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
              onClick={transcribeMidi}
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
    </ThemedCard>
  );
}
