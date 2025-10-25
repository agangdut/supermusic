"use client";
import React, { useEffect, useMemo, useRef, useState } from "react";

function fmtTime(s = 0) {
  if (!Number.isFinite(s)) return "0:00";
  const sign = s < 0 ? "-" : "";
  s = Math.max(0, Math.floor(Math.abs(s)));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${sign}${m}:${String(r).padStart(2, "0")}`;
}

/**
 * Props:
 *  - src?: string                // remote/local URL
 *  - file?: File                 // optional File object
 *  - title?: string
 *  - autoPlay?: boolean
 *  - initialVolume?: number      // 0..1 (default 0.9)
 *  - playbackRates?: number[]    // default [0.75, 1, 1.25, 1.5, 2]
 *  - onEnded?: () => void
 *
 * Exposes ref with .element to get the underlying <audio>.
 */
export default function Player({
  src,
  file,
  title = "Audio",
  autoPlay = false,
  initialVolume = 0.9,
  playbackRates = [0.75, 1, 1.25, 1.5, 2],
  onEnded,
}) {
  const audioRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [playing, setPlaying] = useState(false);
  const [cur, setCur] = useState(0);
  const [dur, setDur] = useState(NaN);
  const [muted, setMuted] = useState(false);
  const [vol, setVol] = useState(initialVolume);
  const [rate, setRate] = useState(1);

  // Prefer File object if provided
  const objectUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  const effectiveSrc = objectUrl || src || "";

  useEffect(() => () => objectUrl && URL.revokeObjectURL(objectUrl), [objectUrl]);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;

    const onLoadedMeta = () => {
      setDur(el.duration);
      setReady(true);
      setError("");
      el.volume = vol;
      el.playbackRate = rate;
      if (autoPlay) el.play().catch(() => {}); // autoplay often blocked
    };
    const onTime = () => setCur(el.currentTime);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onEnd = () => {
      setPlaying(false);
      onEnded?.();
    };
    const onErr = () => {
      setError("Failed to load audio.");
      setReady(false);
      setPlaying(false);
    };

    el.addEventListener("loadedmetadata", onLoadedMeta);
    el.addEventListener("timeupdate", onTime);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("ended", onEnd);
    el.addEventListener("error", onErr);

    return () => {
      el.removeEventListener("loadedmetadata", onLoadedMeta);
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("ended", onEnd);
      el.removeEventListener("error", onErr);
    };
  }, [autoPlay, onEnded, rate, vol]);

  const toggle = async () => {
    const el = audioRef.current;
    if (!el) return;
    try {
      if (playing) el.pause();
      else await el.play();
    } catch (e) {
      // Autoplay blocked or other error
    }
  };

  const onSeek = (e) => {
    const el = audioRef.current;
    if (!el) return;
    const next = Number(e.target.value);
    el.currentTime = next;
    setCur(next);
  };

  const onVolume = (e) => {
    const el = audioRef.current;
    if (!el) return;
    const v = Number(e.target.value);
    el.volume = v;
    setVol(v);
    if (v > 0 && muted) {
      el.muted = false;
      setMuted(false);
    }
  };

  const onToggleMute = () => {
    const el = audioRef.current;
    if (!el) return;
    el.muted = !el.muted;
    setMuted(el.muted);
  };

  const onRate = (e) => {
    const el = audioRef.current;
    if (!el) return;
    const r = Number(e.target.value);
    el.playbackRate = r;
    setRate(r);
  };

  return (
    <div className="rounded-xl border bg-white p-3 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold">{title}</h3>
          <p className="mt-0.5 text-xs text-gray-500">
            {fmtTime(cur)} / {fmtTime(dur)}
          </p>
        </div>
        <div className="shrink-0 flex items-center gap-2">
          <button
            onClick={toggle}
            className="rounded-lg border px-3 py-1.5 text-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={!effectiveSrc}
            aria-label={playing ? "Pause" : "Play"}
          >
            {playing ? "⏸" : "▶️"}
          </button>
          <button
            onClick={onToggleMute}
            className="rounded-lg border px-3 py-1.5 text-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            aria-label={muted ? "Unmute" : "Mute"}
          >
            {muted ? "🔇" : "🔊"}
          </button>
          <select
            value={rate}
            onChange={onRate}
            className="rounded-lg border px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
            title="Playback speed"
          >
            {playbackRates.map((r) => (
              <option key={r} value={r}>{r}×</option>
            ))}
          </select>
        </div>
      </div>

      {/* Seek */}
      <div className="mt-3">
        <input
          type="range"
          min={0}
          max={Number.isFinite(dur) ? dur : 0}
          step="0.01"
          value={Number.isFinite(cur) ? cur : 0}
          onChange={onSeek}
          className="w-full accent-blue-600"
          aria-label="Seek"
        />
      </div>

      {/* Volume */}
      <div className="mt-3 flex items-center gap-2">
        <span className="text-xs text-gray-600 w-12">Volume</span>
        <input
          type="range"
          min={0}
          max={1}
          step="0.01"
          value={muted ? 0 : vol}
          onChange={onVolume}
          className="w-full accent-blue-600"
          aria-label="Volume"
        />
        {effectiveSrc && (
          <a
            href={effectiveSrc}
            download
            className="shrink-0 rounded-lg border px-2 py-1 text-xs hover:bg-gray-50"
          >
            download
          </a>
        )}
      </div>

      {/* Hidden native audio (we control it via custom UI) */}
      <audio
        ref={audioRef}
        src={effectiveSrc || undefined}
        preload="metadata"
        className="hidden"
        crossOrigin="anonymous"
      />
      {!effectiveSrc && (
        <p className="mt-2 text-sm text-gray-500">Pick a file or provide a source URL.</p>
      )}
      {error && (
        <p className="mt-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
