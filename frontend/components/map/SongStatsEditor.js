import { useEffect, useState } from "react";

import { getSongStats, voteSongStat } from "@/lib/api";

// The stats listeners can correct, in the order shown
const ROWS = [
  { field: "bpm", kind: "bpm" },
  { field: "key", kind: "text", placeholder: "Am, F#, Bb major or 8A" },
  { field: "genre", kind: "genre" },
  { field: "energy", kind: "score" },
  { field: "valence", kind: "score" },
  { field: "danceability", kind: "score" },
  { field: "acousticness", kind: "score" },
  { field: "year", kind: "number", placeholder: "e.g. 2019" },
  { field: "vibes", kind: "vibes", placeholder: "late night, gym, rainy day" },
];

function show(field, v) {
  if (v == null || v === "") return "—";
  if (Array.isArray(v)) return v.join(", ");
  if (["energy", "valence", "danceability", "acousticness"].includes(field)) return `${Math.round(v * 100)}`;
  if (field === "bpm") return `${Math.round(v)}`;
  return String(v);
}

// What the map should show for a stat after an edit: your answer, else what listeners agreed on
function patchFor(field, value) {
  if (field === "genre") return { genre: value ? value.join(", ") : value };
  if (field === "key") return { key: value, camelot: null };
  return { [field]: value };
}

function Row({ row, stat, genres, track, onSaved, song }) {
  const start = stat.mine ?? stat.shared ?? stat.looked_up ?? track[row.field];
  const [value, setValue] = useState(() => {
    if (row.kind === "score") return start != null ? Math.round(Number(start) * 100) : 50;
    if (row.kind === "genre") return Array.isArray(start) ? start : String(start || "").split(/[;,]\s*/).filter(Boolean);
    if (row.kind === "vibes") return Array.isArray(stat.mine) ? stat.mine.join(", ") : "";
    return start ?? "";
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const send = async (v) => {
    setBusy(true);
    setError(null);
    try {
      const res = await voteSongStat({ ...song, field: row.field, value: v });
      const s = res.stats[row.field];
      onSaved(res, row.field, res.saved ?? s.shared ?? null);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  const genrePick = (i, g) => {
    const next = [...value];
    next[i] = g;
    setValue(next.filter(Boolean).filter((x, j, a) => a.indexOf(x) === j));
  };

  return (
    <div className="rounded-lg border border-white/5 p-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-gray-200">{stat.label}</span>
        <span className="text-[10px] text-gray-500">
          {stat.votes > 0 ? `${stat.votes} listener${stat.votes === 1 ? "" : "s"}` : "no edits yet"}
        </span>
      </div>
      <div className="mt-0.5 space-y-0.5 text-[10px] leading-4 text-gray-500">
        {stat.looked_up != null && <div>Looked up: {show(row.field, stat.looked_up)}{stat.source ? ` (${stat.source})` : ""}</div>}
        {stat.shared != null && <div className="text-emerald-300/80">Listeners agree: {show(row.field, stat.shared)} ({stat.agree} agree), used on everyone&apos;s map</div>}
        {stat.mine != null && <div className="text-sky-300/80">You said: {show(row.field, stat.mine)}</div>}
        {stat.suggested?.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-0.5">
            {stat.suggested.map((s) => (
              <button key={s.tag} type="button"
                onClick={() => setValue((v) => [...new Set([...String(v).split(",").map((x) => x.trim()).filter(Boolean), s.tag])].slice(0, 3).join(", "))}
                className="rounded border border-white/10 px-1 text-[10px] text-gray-300 hover:border-white/30">
                + {s.tag} <span className="text-gray-500">{s.votes}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      <form className="mt-1.5 flex items-center gap-1.5" onSubmit={(e) => { e.preventDefault(); send(value); }}>
        {row.kind === "score" && (
          <>
            <input type="range" min="0" max="100" value={value} onChange={(e) => setValue(Number(e.target.value))}
              className="min-w-0 flex-1 accent-sky-400" aria-label={stat.label} />
            <span className="w-7 text-right text-[11px] tabular-nums text-gray-400">{value}</span>
          </>
        )}
        {row.kind === "bpm" && (
          <>
            <input type="number" min="40" max="250" step="0.5" value={value} onChange={(e) => setValue(e.target.value)}
              className="w-16 rounded border border-white/10 bg-black/30 px-1.5 py-0.5 text-xs text-white" aria-label={stat.label} />
            <button type="button" title="Half time" onClick={() => setValue((v) => Math.round((Number(v) / 2) * 10) / 10)}
              className="rounded border border-white/10 px-1.5 py-0.5 text-[10px] text-gray-300 hover:border-white/30">½</button>
            <button type="button" title="Double time" onClick={() => setValue((v) => Math.round(Number(v) * 2 * 10) / 10)}
              className="rounded border border-white/10 px-1.5 py-0.5 text-[10px] text-gray-300 hover:border-white/30">×2</button>
            <span className="flex-1" />
          </>
        )}
        {(row.kind === "text" || row.kind === "number" || row.kind === "vibes") && (
          <input type={row.kind === "number" ? "number" : "text"} value={value} placeholder={row.placeholder}
            onChange={(e) => setValue(e.target.value)} aria-label={stat.label}
            className="min-w-0 flex-1 rounded border border-white/10 bg-black/30 px-1.5 py-0.5 text-xs text-white placeholder:text-gray-600" />
        )}
        {row.kind === "genre" && (
          <div className="flex min-w-0 flex-1 gap-1">
            {[0, 1].map((i) => (
              <select key={i} value={value[i] || ""} onChange={(e) => genrePick(i, e.target.value)} aria-label={`${stat.label} ${i + 1}`}
                className="min-w-0 flex-1 rounded border border-white/10 bg-black/60 px-1 py-0.5 text-xs text-white">
                <option value="">{i === 0 ? "Pick…" : "(none)"}</option>
                {genres.map((g) => <option key={g} value={g}>{g}</option>)}
              </select>
            ))}
          </div>
        )}
        <button type="submit" disabled={busy}
          className="rounded bg-sky-500/20 px-2 py-0.5 text-[11px] text-sky-100 hover:bg-sky-500/30 disabled:opacity-40">
          Save
        </button>
        {stat.mine != null && (
          <button type="button" disabled={busy} onClick={() => send(null)} title="Take my edit back"
            className="text-[10px] text-gray-500 hover:text-white">Undo</button>
        )}
      </form>
      {error && <p className="mt-1 text-[10px] text-rose-300">{error}</p>}
    </div>
  );
}

/** "Fix this song's stats": correct BPM, key, genre, energy... and tag vibes, shared with other listeners. */
export default function SongStatsEditor({ track, onChange }) {
  const song = { artist: track.artist || "", title: track.title };
  const [view, setView] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    setView(null);
    setError(null);
    getSongStats(song).then((v) => live && setView(v)).catch((e) => live && setError(e.message || String(e)));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [track.artist, track.title]);

  if (error) return <p className="mt-2 text-xs text-rose-300">{error}</p>;
  if (!view) return <p className="mt-2 text-xs text-gray-500">Loading this song&apos;s stats…</p>;

  return (
    <div className="mt-2 space-y-1.5">
      <p className="text-[11px] leading-4 text-gray-400">
        Got something wrong? Your edit changes your map straight away. Once {view.rules.min_agree - 1} more listener
        agrees, it&apos;s used on everyone&apos;s map. Remap to move the star.
      </p>
      {ROWS.map((row) => (
        <Row key={`${row.field}-${view.song_key}`} row={row} stat={view.stats[row.field]} genres={view.genres} track={track} song={song}
          onSaved={(res, field, value) => { setView(res); onChange(patchFor(field, value)); }} />
      ))}
    </div>
  );
}
