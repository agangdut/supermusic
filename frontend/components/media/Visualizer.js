"use client";
import React, { useEffect, useMemo, useRef, useState } from "react";

/**
 * Canvas-based audio visualizer using Web Audio API.
 *
 * Preferred usage: pass an audioRef from your Player.
 * Fallback: pass a `src` and this component will create its own <audio>.
 *
 * Props:
 *  - audioRef?: React.RefObject<HTMLAudioElement>
 *  - src?: string
 *  - height?: number (default 120)
 *  - mode?: "bars" | "wave" (default "bars")
 *  - fftSize?: 32..32768 (default 2048)
 *  - smoothing?: 0..1 (default 0.8)
 *  - background?: string (CSS color, default "transparent")
 *  - color?: string (CSS color, default "#3b82f6")
 *  - autoPlayWhenSrc?: boolean (default false)  // only when using `src`
 */
export default function Visualizer({
  audioRef,
  src,
  height = 120,
  mode = "bars",
  fftSize = 2048,
  smoothing = 0.8,
  background = "transparent",
  color = "#3b82f6",
  autoPlayWhenSrc = false,
}) {
  const localAudioRef = useRef(null);
  const canvasRef = useRef(null);
  const ctxRef = useRef(null);
  const analyserRef = useRef(null);
  const rafRef = useRef(0);
  const [needsResume, setNeedsResume] = useState(false);

  const usingLocal = !audioRef && src;
  const effectiveAudioRef = usingLocal ? localAudioRef : audioRef;

  // Create (or reuse) AudioContext
  const AC = useMemo(() => {
    if (typeof window === "undefined") return null;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    return Ctx ? new Ctx() : null;
  }, []);

  // Connect audio element -> analyser -> destination
  useEffect(() => {
    if (!AC || !effectiveAudioRef?.current) return;
    const el = effectiveAudioRef.current;

    // Safari/Chrome require user gesture to start/resume
    if (AC.state !== "running") {
      setNeedsResume(true);
    }

    const analyser = AC.createAnalyser();
    analyser.fftSize = fftSize;
    analyser.smoothingTimeConstant = smoothing;

    let source;
    try {
      source = AC.createMediaElementSource(el);
      source.connect(analyser);
      analyser.connect(AC.destination);
    } catch (e) {
      // If already connected or CORS issue, ignore
    }

    analyserRef.current = analyser;

    return () => {
      try {
        analyser.disconnect();
        source && source.disconnect();
      } catch {}
    };
  }, [AC, effectiveAudioRef, fftSize, smoothing]);

  // Resize canvas to device pixel ratio
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resize = () => {
      const dpr = Math.max(1, window.devicePixelRatio || 1);
      const width = canvas.clientWidth;
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      const ctx = canvas.getContext("2d");
      ctx.scale(dpr, dpr);
      ctxRef.current = ctx;
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [height]);

  // Draw loop
  useEffect(() => {
    const analyser = analyserRef.current;
    const ctx = ctxRef.current;
    const canvas = canvasRef.current;
    if (!analyser || !ctx || !canvas) return;

    const W = canvas.clientWidth;
    const H = height;

    const bufferLen =
      mode === "bars" ? analyser.frequencyBinCount : analyser.fftSize;
    const data =
      mode === "bars"
        ? new Uint8Array(bufferLen)
        : new Uint8Array(analyser.fftSize);

    const draw = () => {
      ctx.clearRect(0, 0, W, H);
      if (background && background !== "transparent") {
        ctx.fillStyle = background;
        ctx.fillRect(0, 0, W, H);
      }

      if (mode === "bars") {
        analyser.getByteFrequencyData(data);
        const barCount = Math.min(96, Math.floor(W / 6));
        const step = Math.floor(data.length / barCount);
        const barW = (W / barCount) * 0.66;

        for (let i = 0; i < barCount; i++) {
          const v = data[i * step] / 255;
          const barH = Math.max(2, v * (H - 8));
          const x = i * (W / barCount);
          const y = H - barH;
          ctx.fillStyle = color;
          ctx.fillRect(x, y, barW, barH);
        }
      } else {
        analyser.getByteTimeDomainData(data);
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        const slice = W / data.length;
        for (let i = 0; i < data.length; i++) {
          const v = data[i] / 128.0; // ~[0,2]
          const y = (v * H) / 2;
          const x = i * slice;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      rafRef.current = requestAnimationFrame(draw);
    };

    rafRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(rafRef.current);
  }, [height, color, background, mode]);

  // Build local audio element if using `src`
  useEffect(() => {
    if (!usingLocal) return;
    const el = localAudioRef.current;
    if (!el) return;
    el.crossOrigin = "anonymous";
    if (autoPlayWhenSrc) {
      el.play().catch(() => {}); // may require resume
    }
  }, [usingLocal, autoPlayWhenSrc, src]);

  const tryResume = async () => {
    if (!AC) return;
    try {
      await AC.resume();
      setNeedsResume(false);
    } catch {}
  };

  return (
    <div className="rounded-xl border bg-white p-3 shadow-sm">
      <div className="relative">
        <canvas
          ref={canvasRef}
          style={{ width: "100%", height }}
          className="block rounded-md bg-transparent"
          aria-label="Audio visualizer"
        />
        {needsResume && (
          <button
            onClick={tryResume}
            className="absolute inset-0 m-auto h-9 w-40 rounded-lg border bg-white/90 text-sm shadow hover:bg-white"
            title="Resume audio"
          >
            Click to Enable Audio
          </button>
        )}
      </div>

      {usingLocal && (
        <audio
          ref={localAudioRef}
          src={src}
          className="mt-2 w-full"
          controls
          preload="metadata"
          crossOrigin="anonymous"
        />
      )}
    </div>
  );
}
