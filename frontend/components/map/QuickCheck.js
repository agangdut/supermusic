import { useEffect, useRef, useState } from "react";

import { getSongCheck, voteSongStat } from "@/lib/api";
import { patchFor } from "@/components/map/SongStatsEditor";

// ---- sound helpers -------------------------------------------------------------------------

let audioCtx = null;

/** Play a chord (MIDI note numbers) as a soft piano-ish tone for about a second. */
export function playChord(notes) {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const now = audioCtx.currentTime;
    notes.forEach((n, i) => {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = "triangle";
      osc.frequency.value = 440 * 2 ** ((n - 69) / 12);
      const start = now + i * 0.04;
      gain.gain.setValueAtTime(0, start);
      gain.gain.linearRampToValueAtTime(0.18, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, start + 1.4);
      osc.connect(gain).connect(audioCtx.destination);
      osc.start(start);
      osc.stop(start + 1.5);
    });
  } catch {
    // No audio in this browser: the labels still work
  }
}

/** Tap along to the song; the tempo is the median gap between the last few taps. */
export function TapTempo({ onTempo }) {
  const taps = useRef([]);
  const [bpm, setBpm] = useState(null);
  const tap = () => {
    const now = performance.now();
    const t = taps.current;
    if (t.length && now - t[t.length - 1] > 2000) t.length = 0; // a pause starts over
    t.push(now);
    if (t.length > 9) t.shift();
    if (t.length >= 4) {
      const gaps = t.slice(1).map((x, i) => x - t[i]).sort((a, b) => a - b);
      const mid = gaps[Math.floor(gaps.length / 2)];
      setBpm(Math.round((60000 / mid) * 2) / 2);
    }
  };
  return (
    <div className="flex items-center gap-2">
      <button type="button" onClick={tap}
        className="h-12 w-12 shrink-0 select-none rounded-full border border-sky-300/40 bg-sky-400/10 text-[11px] font-semibold text-sky-100 active:scale-95 active:bg-sky-400/30">
        Tap
      </button>
      <div className="min-w-0 flex-1 text-[11px] leading-4 text-gray-400">
        {bpm ? <>You&apos;re tapping <span className="font-semibold text-white">{bpm} BPM</span></> : "Tap along to the beat, 4 times or more"}
      </div>
      {bpm && (
        <button type="button" onClick={() => onTempo(bpm)}
          className="rounded bg-sky-500/20 px-2 py-1 text-[11px] text-sky-100 hover:bg-sky-500/30">Use {Math.round(bpm)}</button>
      )}
    </div>
  );
}

// ---- the card ------------------------------------------------------------------------------

function resultLine(check) {
  if (!check) return "Saved.";
  const maps = check.reach > 0 ? ` This song is on ${check.reach} public map${check.reach === 1 ? "" : "s"}.` : "";
  if (check.settled) return `Settled: ${check.agree} listeners agree, so nobody needs to be asked again.${maps}`;
  if (check.agreed) return `Listeners agree (${check.agree}), so it's now on everyone's map.${maps}`;
  return `Saved to your map. When one more listener agrees, it goes on everyone's map.${maps}`;
}

/**
 * One yes/no question about a song's stats. Yes saves a vote for the value shown; No offers the
 * likely alternatives (and a tap-along tempo button, or chords to compare); Not sure skips.
 */
export function CheckCard({ q, onAnswered, onNext, onSkip, onMore, nextLabel = "Next check", tone = "map" }) {
  const [step, setStep] = useState("ask"); // ask | no | done
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [check, setCheck] = useState(null);
  const [genre, setGenre] = useState("");

  useEffect(() => { setStep("ask"); setError(null); setCheck(null); setGenre(""); }, [q]);

  const send = async (value) => {
    setBusy(true);
    setError(null);
    try {
      const res = await voteSongStat({ artist: q.artist, title: q.title, field: q.field, value });
      setCheck(res.check);
      setStep("done");
      onAnswered?.(res, q.field, res.saved ?? value);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  const big = tone === "quiz";
  const btn = `rounded-lg border px-3 ${big ? "py-2 text-sm" : "py-1 text-xs"} transition disabled:opacity-40`;

  return (
    <div className={`rounded-xl border border-emerald-300/20 bg-emerald-300/[0.05] ${big ? "p-4" : "p-3"}`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-200/80">Quick check</span>
        <span className="text-[10px] text-gray-500">
          {q.agree > 0 ? `${q.agree} of ${q.settled_at} listeners agree so far` : "no one has checked this yet"}
        </span>
      </div>
      <p className={`mt-1 font-medium text-white ${big ? "text-base" : "text-sm"}`}>{q.prompt}</p>

      {step === "ask" && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {q.chord && (
            <button type="button" onClick={() => playChord(q.chord)} title={`Play a ${q.shown} chord`}
              className={`${btn} border-white/15 text-gray-200 hover:border-white/40`}>▶ {q.shown}</button>
          )}
          <button type="button" disabled={busy} onClick={() => send(q.value)}
            className={`${btn} border-emerald-300/40 bg-emerald-400/10 text-emerald-100 hover:bg-emerald-400/20`}>Yes</button>
          <button type="button" disabled={busy} onClick={() => setStep("no")}
            className={`${btn} border-white/15 text-gray-200 hover:border-white/40`}>No</button>
          <button type="button" disabled={busy} onClick={() => (onSkip || onNext)?.()}
            className={`${btn} border-transparent text-gray-500 hover:text-white`}>Not sure</button>
        </div>
      )}

      {step === "no" && (
        <div className="mt-2 space-y-2">
          <p className="text-[11px] text-gray-400">What is it, then?</p>
          {q.field === "bpm" && <TapTempo onTempo={send} />}
          {q.field === "genre" ? (
            <div className="flex gap-1.5">
              <select value={genre} onChange={(e) => setGenre(e.target.value)} aria-label="Genre"
                className="min-w-0 flex-1 rounded border border-white/10 bg-black/60 px-1.5 py-1 text-xs text-white">
                <option value="">Pick a genre…</option>
                {q.alternatives.map((a) => <option key={a.label} value={a.label}>{a.label}</option>)}
              </select>
              <button type="button" disabled={busy || !genre} onClick={() => send([genre])}
                className={`${btn} border-emerald-300/40 bg-emerald-400/10 text-emerald-100`}>Save</button>
            </div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {q.alternatives.map((a) => (
                <span key={a.label} className="flex">
                  {a.chord && (
                    <button type="button" onClick={() => playChord(a.chord)} title={`Play a ${a.label} chord`}
                      className={`${btn} rounded-r-none border-white/15 text-gray-300 hover:border-white/40`}>▶</button>
                  )}
                  <button type="button" disabled={busy} onClick={() => send(a.value)}
                    className={`${btn} ${a.chord ? "rounded-l-none border-l-0" : ""} border-white/15 text-gray-100 hover:border-emerald-300/50`}>
                    {a.label}
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className="flex gap-3">
            <button type="button" onClick={() => setStep("ask")} className="text-[10px] text-gray-500 hover:text-white">← Back</button>
            {onMore && q.field !== "genre" && (
              <button type="button" onClick={onMore} className="text-[10px] text-sky-300 hover:underline">Something else? Type it in</button>
            )}
          </div>
        </div>
      )}

      {step === "done" && (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <p className="min-w-0 flex-1 text-[11px] leading-4 text-emerald-200/90">✓ {resultLine(check)}</p>
          {onNext && (
            <button type="button" onClick={onNext}
              className={`${btn} border-white/15 text-gray-100 hover:border-white/40`}>{nextLabel} →</button>
          )}
        </div>
      )}
      {error && <p className="mt-1 text-[11px] text-rose-300">{error}</p>}
    </div>
  );
}

/**
 * On the map: asks about the selected song (one of your most played, with a stat listeners
 * haven't settled). When this song has nothing left to ask, offers your next song to check.
 */
export default function QuickCheck({ track, onChange, onNextSong, songsLeft, onMore }) {
  const [q, setQ] = useState(undefined);
  const [skip, setSkip] = useState([]); // stats you said you're not sure about
  const [round, setRound] = useState(0);

  useEffect(() => { setSkip([]); }, [track.artist, track.title]);
  useEffect(() => {
    let live = true;
    setQ(undefined);
    getSongCheck({ artist: track.artist, title: track.title, bpm: track.bpm, key: track.key, genre: track.genre, year: track.year, skip })
      .then((r) => live && setQ(r.question))
      .catch(() => live && setQ(null));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [track.artist, track.title, round, skip]);

  if (q === undefined) return null;
  if (!q) {
    return onNextSong && songsLeft > 0 ? (
      <button type="button" onClick={onNextSong} className="mt-2 text-[11px] text-emerald-300 hover:underline">
        ✓ All checked here. {songsLeft} more of your top songs need a quick check →
      </button>
    ) : null;
  }
  return (
    <div className="mt-2">
      <CheckCard q={q}
        onAnswered={(res, field, value) => onChange(patchFor(field, value))}
        onSkip={() => setSkip((s) => [...s, q.field])}
        onMore={onMore}
        onNext={() => (q.left > 1 ? setRound((r) => r + 1) : onNextSong ? onNextSong() : setQ(null))}
        nextLabel={q.left > 1 ? "Next question" : "Next song"} />
    </div>
  );
}
