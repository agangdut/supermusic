// Plays a MIDI file in the browser with real instrument samples, and draws a
// scrolling piano roll. Each track can be muted or soloed.
//
// Samples are General MIDI soundfonts streamed by `smplr` (from the
// gleitz/midi-js-soundfonts CDN), so the first play of an instrument takes
// a moment to load.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Midi } from "@tonejs/midi";
import { DrumMachine, Soundfont, getSoundfontNames } from "smplr";

const TRACK_COLORS = ["#a78bfa", "#38bdf8", "#f472b6", "#34d399", "#fbbf24", "#fb7185", "#22d3ee", "#c084fc", "#a3e635", "#f97316"];
const LOOKAHEAD = 0.4; // seconds of notes scheduled ahead of the playhead

function soundfontName(track) {
  const known = new Set(getSoundfontNames());
  const name = (track.instrument?.name || "").toLowerCase().replace(/[()]/g, "").trim().replace(/\s+/g, "_");
  if (known.has(name)) return name;
  // YourMT3+ / Stems use friendly track names; map the common ones
  const n = (track.name || "").toLowerCase();
  if (n.includes("vocal") || n.includes("sing") || n.includes("voice")) return "voice_oohs";
  if (n.includes("bass")) return "electric_bass_finger";
  if (n.includes("guitar")) return "electric_guitar_clean";
  if (n.includes("string")) return "string_ensemble_1";
  return "acoustic_grand_piano";
}

function drumSample(names, midiNote) {
  const pick = (...keys) => names.find((s) => keys.some((k) => s.toLowerCase().includes(k)));
  if (midiNote === 35 || midiNote === 36) return pick("kick", "bd");
  if (midiNote === 38 || midiNote === 40) return pick("snare", "sd");
  if (midiNote === 39) return pick("clap", "cp");
  if ([42, 44].includes(midiNote)) return pick("hihat-close", "closed", "hh", "ch");
  if (midiNote === 46) return pick("hihat-open", "open", "oh");
  if ([49, 51, 52, 55, 57, 59].includes(midiNote)) return pick("cymbal", "crash", "ride", "cy");
  if (midiNote >= 41 && midiNote <= 50) return pick("tom", "lt", "mt", "ht");
  return pick("snare", "sd") || names[0];
}

const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

export default function MidiPlayer({ url, title }) {
  const [midi, setMidi] = useState(null);
  const [error, setError] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [loadingSounds, setLoadingSounds] = useState(false);
  const [position, setPosition] = useState(0);
  const [muted, setMuted] = useState({});
  const [solo, setSolo] = useState(null);

  const ctxRef = useRef(null);
  const playersRef = useRef({});
  const startRef = useRef({ ctxTime: 0, offset: 0 });
  const scheduledRef = useRef(0);
  const timerRef = useRef(null);
  const rafRef = useRef(null);
  const canvasRef = useRef(null);
  const stateRef = useRef({ muted, solo });
  stateRef.current = { muted, solo };

  // Load and parse the file
  useEffect(() => {
    let cancelled = false;
    setMidi(null);
    setError(null);
    setPosition(0);
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`Couldn't load the MIDI file (${r.status})`);
        return r.arrayBuffer();
      })
      .then((buf) => !cancelled && setMidi(new Midi(buf)))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [url]);

  const tracks = useMemo(
    () => (midi ? midi.tracks.map((t, i) => ({ t, i })).filter(({ t }) => t.notes.length > 0) : []),
    [midi],
  );
  const duration = midi?.duration || 0;
  const pitchRange = useMemo(() => {
    const ps = tracks.flatMap(({ t }) => (t.instrument.percussion ? [] : t.notes.map((n) => n.midi)));
    return ps.length ? [Math.min(...ps) - 2, Math.max(...ps) + 2] : [36, 96];
  }, [tracks]);

  const audible = (i) => {
    const { muted: m, solo: s } = stateRef.current;
    return s != null ? s === i : !m[i];
  };

  // ---- Piano roll ---------------------------------------------------------
  const draw = useCallback(
    (pos) => {
      const c = canvasRef.current;
      if (!c || !midi) return;
      const dpr = window.devicePixelRatio || 1;
      const w = c.clientWidth;
      const h = c.clientHeight;
      if (c.width !== w * dpr) {
        c.width = w * dpr;
        c.height = h * dpr;
      }
      const g = c.getContext("2d");
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, h);
      const windowSecs = 10;
      const t0 = Math.max(0, pos - windowSecs * 0.25);
      const x = (t) => ((t - t0) / windowSecs) * w;
      const [lo, hi] = pitchRange;
      const rowH = h / (hi - lo + 1);
      // C lines
      g.fillStyle = "rgba(255,255,255,0.04)";
      for (let p = lo; p <= hi; p++) if (p % 12 === 0) g.fillRect(0, h - (p - lo + 1) * rowH, w, 1);
      tracks.forEach(({ t, i }, k) => {
        const on = audible(i);
        g.fillStyle = TRACK_COLORS[k % TRACK_COLORS.length];
        g.globalAlpha = on ? 0.9 : 0.15;
        for (const n of t.notes) {
          if (n.time + n.duration < t0 || n.time > t0 + windowSecs) continue;
          const pitch = t.instrument.percussion ? lo + ((n.midi - 35) % (hi - lo)) : n.midi;
          const active = pos >= n.time && pos < n.time + n.duration;
          g.fillRect(x(n.time), h - (pitch - lo + 1) * rowH, Math.max(2, (n.duration / windowSecs) * w), Math.max(2, rowH - 1));
          if (active && on) {
            g.save();
            g.globalAlpha = 1;
            g.shadowColor = g.fillStyle;
            g.shadowBlur = 12;
            g.fillRect(x(n.time), h - (pitch - lo + 1) * rowH, Math.max(2, (n.duration / windowSecs) * w), Math.max(2, rowH - 1));
            g.restore();
          }
        }
      });
      g.globalAlpha = 1;
      g.fillStyle = "#ffffff";
      g.fillRect(x(pos), 0, 1.5, h);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [midi, tracks, pitchRange],
  );

  useEffect(() => draw(position), [draw, position, muted, solo]);

  // ---- Playback -------------------------------------------------------------
  const ensurePlayers = async () => {
    if (!ctxRef.current) ctxRef.current = new AudioContext();
    const ctx = ctxRef.current;
    const need = tracks.filter(({ i }) => !playersRef.current[i]);
    if (!need.length) return ctx;
    setLoadingSounds(true);
    await Promise.all(
      need.map(async ({ t, i }) => {
        const p = t.instrument.percussion
          ? new DrumMachine(ctx, { instrument: "TR-808" })
          : new Soundfont(ctx, { instrument: soundfontName(t) });
        await p.load;
        playersRef.current[i] = p;
      }),
    );
    setLoadingSounds(false);
    return ctx;
  };

  const now = () => {
    const { ctxTime, offset } = startRef.current;
    return offset + (ctxRef.current.currentTime - ctxTime);
  };

  const schedule = () => {
    const ctx = ctxRef.current;
    const from = scheduledRef.current;
    const to = now() + LOOKAHEAD;
    for (const { t, i } of tracks) {
      if (!audible(i)) continue;
      const p = playersRef.current[i];
      if (!p) continue;
      const drumNames = t.instrument.percussion ? p.getSampleNames() : null;
      for (const n of t.notes) {
        if (n.time < from || n.time >= to) continue;
        const when = startRef.current.ctxTime + (n.time - startRef.current.offset);
        const velocity = Math.round(n.velocity * 127);
        if (drumNames) {
          const s = drumSample(drumNames, n.midi);
          if (s) p.start({ note: s, velocity, time: when });
        } else {
          p.start({ note: n.midi, velocity, time: when, duration: Math.max(0.05, n.duration) });
        }
      }
    }
    scheduledRef.current = to;
  };

  const stopAll = () => {
    clearInterval(timerRef.current);
    cancelAnimationFrame(rafRef.current);
    Object.values(playersRef.current).forEach((p) => p.stop?.());
  };

  const play = async () => {
    const ctx = await ensurePlayers();
    await ctx.resume();
    const from = position >= duration ? 0 : position;
    startRef.current = { ctxTime: ctx.currentTime + 0.1, offset: from };
    scheduledRef.current = from;
    setPlaying(true);
    schedule();
    timerRef.current = setInterval(schedule, 100);
    const tick = () => {
      const pos = now();
      if (pos >= duration) {
        stopAll();
        setPlaying(false);
        setPosition(duration);
        return;
      }
      setPosition(pos);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  };

  const pause = () => {
    stopAll();
    setPlaying(false);
    setPosition(now());
  };

  const seek = (s) => {
    const wasPlaying = playing;
    if (wasPlaying) stopAll();
    setPosition(s);
    if (wasPlaying) {
      startRef.current = { ctxTime: ctxRef.current.currentTime + 0.05, offset: s };
      scheduledRef.current = s;
      schedule();
      timerRef.current = setInterval(schedule, 100);
      const tick = () => {
        const pos = now();
        if (pos >= duration) return pause();
        setPosition(pos);
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
    }
  };

  useEffect(() => () => {
    stopAll();
    ctxRef.current?.close?.();
  }, []);
  useEffect(() => {
    // New file: drop the old instruments and stop
    stopAll();
    setPlaying(false);
    playersRef.current = {};
    setMuted({});
    setSolo(null);
  }, [url]);

  if (error) return <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</div>;
  if (!midi) return <div className="p-4 text-sm text-gray-400">Loading MIDI…</div>;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <button
          onClick={playing ? pause : play}
          disabled={loadingSounds}
          className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-gradient-to-br from-fuchsia-500 to-indigo-500 text-white shadow-lg shadow-fuchsia-500/30 disabled:opacity-50"
          aria-label={playing ? "Pause" : "Play"}
        >
          {loadingSounds ? "…" : playing ? "❚❚" : "▶"}
        </button>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-gray-100">{title || "MIDI"}</div>
          <input
            type="range" min={0} max={duration} step={0.1} value={position}
            onChange={(e) => seek(Number(e.target.value))}
            className="w-full accent-fuchsia-500"
          />
        </div>
        <div className="shrink-0 text-xs tabular-nums text-gray-400">{fmt(position)} / {fmt(duration)}</div>
      </div>
      {loadingSounds && <div className="text-[11px] text-gray-500">Loading instrument sounds…</div>}

      <canvas ref={canvasRef} className="h-48 w-full rounded-lg border border-white/10 bg-[#070b16]" />

      <div className="flex flex-wrap gap-2">
        {tracks.map(({ t, i }, k) => {
          const color = TRACK_COLORS[k % TRACK_COLORS.length];
          const on = solo != null ? solo === i : !muted[i];
          return (
            <div key={i} className={`flex items-center gap-1 rounded-lg border px-2 py-1 text-xs ${on ? "border-white/15 text-gray-200" : "border-white/5 text-gray-500"}`}>
              <span className="h-2 w-2 rounded-full" style={{ background: color }} />
              <span>{t.name || t.instrument.name}</span>
              <span className="text-gray-500">· {t.notes.length}</span>
              <button className="ml-1 rounded px-1 hover:bg-white/10" title="Mute" onClick={() => setMuted((m) => ({ ...m, [i]: !m[i] }))}>
                {muted[i] ? "🔇" : "🔈"}
              </button>
              <button className={`rounded px-1 hover:bg-white/10 ${solo === i ? "text-amber-300" : ""}`} title="Solo" onClick={() => setSolo((s) => (s === i ? null : i))}>
                S
              </button>
            </div>
          );
        })}
      </div>
      <a href={url} download className="inline-block text-xs text-indigo-300 underline-offset-2 hover:underline">Download .mid</a>
    </div>
  );
}
