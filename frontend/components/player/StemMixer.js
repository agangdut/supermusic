// Plays several audio files (stems) in sync, with a fader, mute and solo per stem.
import { useEffect, useRef, useState } from "react";

const COLORS = { vocals: "#f472b6", drums: "#fbbf24", bass: "#38bdf8", guitar: "#34d399", piano: "#a78bfa", other: "#94a3b8" };
const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

function Waveform({ buffer, color, position, duration }) {
  const ref = useRef(null);
  useEffect(() => {
    const c = ref.current;
    if (!c || !buffer) return;
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth;
    const h = c.clientHeight;
    c.width = w * dpr;
    c.height = h * dpr;
    const g = c.getContext("2d");
    g.scale(dpr, dpr);
    const data = buffer.getChannelData(0);
    const step = Math.max(1, Math.floor(data.length / w));
    g.fillStyle = color;
    for (let x = 0; x < w; x++) {
      let peak = 0;
      for (let i = x * step; i < (x + 1) * step && i < data.length; i += 16) peak = Math.max(peak, Math.abs(data[i]));
      const bar = Math.max(1, peak * h);
      g.fillRect(x, (h - bar) / 2, 1, bar);
    }
  }, [buffer, color]);
  return (
    <div className="relative h-8 flex-1">
      <canvas ref={ref} className="h-full w-full opacity-70" />
      {duration > 0 && <div className="absolute top-0 h-full w-px bg-white" style={{ left: `${(position / duration) * 100}%` }} />}
    </div>
  );
}

export default function StemMixer({ stems }) {
  const entries = Object.entries(stems || {}).filter(([, u]) => typeof u === "string" && /\.(wav|mp3|flac|ogg)$/i.test(u));
  const [buffers, setBuffers] = useState({});
  const [loading, setLoading] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [vol, setVol] = useState({});
  const [muted, setMuted] = useState({});
  const [solo, setSolo] = useState(null);
  const ctxRef = useRef(null);
  const nodesRef = useRef({});
  const startRef = useRef({ ctxTime: 0, offset: 0 });
  const rafRef = useRef(null);
  const key = entries.map(([k, u]) => k + u).join("|");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setBuffers({});
    ctxRef.current = ctxRef.current || new AudioContext();
    Promise.all(
      entries.map(async ([name, url]) => {
        const r = await fetch(url);
        const b = await ctxRef.current.decodeAudioData(await r.arrayBuffer());
        return [name, b];
      }),
    ).then((pairs) => {
      if (!cancelled) {
        setBuffers(Object.fromEntries(pairs));
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
      stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const duration = Math.max(0, ...Object.values(buffers).map((b) => b.duration));
  const gainFor = (name) => (solo ? (solo === name ? 1 : 0) : muted[name] ? 0 : vol[name] ?? 1);

  useEffect(() => {
    for (const [name, n] of Object.entries(nodesRef.current)) n.gain.gain.value = gainFor(name);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vol, muted, solo]);

  function stop() {
    cancelAnimationFrame(rafRef.current);
    for (const n of Object.values(nodesRef.current)) {
      try { n.src.stop(); } catch {}
    }
    nodesRef.current = {};
  }

  const now = () => startRef.current.offset + (ctxRef.current.currentTime - startRef.current.ctxTime);

  const start = async (from) => {
    const ctx = ctxRef.current;
    await ctx.resume();
    stop();
    const at = ctx.currentTime + 0.05;
    for (const [name, b] of Object.entries(buffers)) {
      const src = ctx.createBufferSource();
      src.buffer = b;
      const gain = ctx.createGain();
      gain.gain.value = gainFor(name);
      src.connect(gain).connect(ctx.destination);
      src.start(at, Math.min(from, b.duration));
      nodesRef.current[name] = { src, gain };
    }
    startRef.current = { ctxTime: at, offset: from };
    setPlaying(true);
    const tick = () => {
      const p = now();
      if (p >= duration) {
        stop();
        setPlaying(false);
        setPosition(0);
        return;
      }
      setPosition(p);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  };

  const pause = () => {
    setPosition(now());
    stop();
    setPlaying(false);
  };

  if (!entries.length) return null;
  if (loading) return <div className="p-4 text-sm text-gray-400">Loading stems…</div>;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <button
          onClick={() => (playing ? pause() : start(position))}
          className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-gradient-to-br from-fuchsia-500 to-indigo-500 text-white shadow-lg shadow-fuchsia-500/30"
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <input
          type="range" min={0} max={duration} step={0.1} value={position}
          onChange={(e) => { const s = Number(e.target.value); setPosition(s); if (playing) start(s); }}
          className="flex-1 accent-fuchsia-500"
        />
        <div className="text-xs tabular-nums text-gray-400">{fmt(position)} / {fmt(duration)}</div>
      </div>
      <div className="space-y-2">
        {entries.map(([name, url]) => {
          const color = COLORS[name.toLowerCase()] || "#94a3b8";
          return (
            <div key={name} className="flex items-center gap-3">
              <span className="w-16 truncate text-xs capitalize text-gray-300">{name}</span>
              <button className={`rounded px-1.5 py-0.5 text-[11px] ${muted[name] ? "bg-white/10 text-gray-500" : "text-gray-300 hover:bg-white/10"}`} onClick={() => setMuted((m) => ({ ...m, [name]: !m[name] }))}>M</button>
              <button className={`rounded px-1.5 py-0.5 text-[11px] ${solo === name ? "bg-amber-400/20 text-amber-300" : "text-gray-300 hover:bg-white/10"}`} onClick={() => setSolo((s) => (s === name ? null : name))}>S</button>
              <Waveform buffer={buffers[name]} color={color} position={position} duration={duration} />
              <input type="range" min={0} max={1.5} step={0.05} value={vol[name] ?? 1} onChange={(e) => setVol((v) => ({ ...v, [name]: Number(e.target.value) }))} className="w-20 accent-fuchsia-500" title="Volume" />
              <a href={url} download className="text-[11px] text-indigo-300 hover:underline">↓</a>
            </div>
          );
        })}
      </div>
    </div>
  );
}
