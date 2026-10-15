import { useEffect, useState } from "react";

import { getCommunityActivity, tasteMatch } from "@/lib/api";

function ago(seconds) {
  const s = Date.now() / 1000 - seconds;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

function show(r) {
  const v = r.value;
  if (Array.isArray(v)) return v.join(", ");
  if (["energy", "valence", "danceability", "acousticness"].includes(r.field)) return `${Math.round(v * 100)}/100`;
  return String(v);
}

function search(t) {
  return `https://www.youtube.com/results?search_query=${encodeURIComponent([t.artist, t.title].filter(Boolean).join(" "))}`;
}

/** The "People" tab: shared maps closest to yours, and the latest song edits from everyone. */
export default function PeoplePanel({ source, onSongTitle }) {
  const [matches, setMatches] = useState(null);
  const [activity, setActivity] = useState(null);
  const [error, setError] = useState(null);
  const sourceKey = JSON.stringify(source || null);

  useEffect(() => {
    let live = true;
    setMatches(null);
    setError(null);
    if (source) tasteMatch(source).then((r) => live && setMatches(r.matches)).catch((e) => live && setError(e.message || String(e)));
    getCommunityActivity(15).then((a) => live && setActivity(a)).catch(() => {});
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceKey]);

  return (
    <div className="space-y-4">
      <section>
        <h3 className="text-[11px] uppercase tracking-wider text-gray-500">Listeners like you</h3>
        <p className="mt-1 text-[11px] leading-5 text-gray-500">
          Maps people shared publicly, closest to yours by the artists you both play, with songs of theirs you don&apos;t have.
        </p>
        {!source && <p className="mt-2 text-xs text-gray-500">This shared map has no song list to compare.</p>}
        {source && !matches && !error && <p className="mt-2 text-xs text-gray-500">Comparing with shared maps…</p>}
        {error && <p className="mt-2 text-xs text-rose-300">{error}</p>}
        {matches?.length === 0 && (
          <p className="mt-2 text-xs text-gray-500">No public map shares an artist with yours yet. Share yours (and tick “list it”) so others can find you.</p>
        )}
        <div className="mt-2 space-y-2">
          {matches?.map((m) => (
            <div key={m.share_id} className="rounded-xl border border-white/5 p-3">
              <div className="flex items-baseline justify-between gap-2">
                <a href={`/?share=${m.share_id}`} className="min-w-0 truncate text-sm font-medium text-white hover:underline">
                  {m.title}{m.by ? <span className="text-gray-500"> by {m.by}</span> : null}
                </a>
                <span className="shrink-0 text-sm font-semibold text-emerald-300">{m.match}%</span>
              </div>
              <div className="mt-1 text-[11px] text-gray-500">
                {m.shared_artists} artists and {m.shared_songs} songs in common, out of their {m.songs}
              </div>
              {m.top_shared_artists.length > 0 && (
                <div className="mt-0.5 truncate text-[11px] text-gray-400">You both play {m.top_shared_artists.join(", ")}</div>
              )}
              {m.picks.length > 0 && (
                <div className="mt-2 space-y-1">
                  <div className="text-[10px] uppercase tracking-wider text-gray-600">Try from their map</div>
                  {m.picks.slice(0, 5).map((p) => (
                    <a key={`${p.artist}|${p.title}`} href={search(p)} target="_blank" rel="noopener noreferrer"
                      className="block truncate text-xs text-gray-300 hover:text-white">
                      {p.title} <span className="text-gray-500">· {p.artist}{p.you_like_artist ? " (you play them)" : ""}</span>
                    </a>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3 className="text-[11px] uppercase tracking-wider text-gray-500">Latest song fixes</h3>
        {activity && (
          <p className="mt-1 text-[11px] leading-5 text-gray-500">
            {activity.listeners} listener{activity.listeners === 1 ? "" : "s"} have fixed {activity.songs} song{activity.songs === 1 ? "" : "s"};{" "}
            {activity.songs_looked_up.toLocaleString()} songs looked up online are shared. Click a song on the map and choose
            &ldquo;Fix stats&rdquo; to help.
          </p>
        )}
        <div className="mt-2 space-y-1.5">
          {activity?.recent.map((r, i) => (
            <div key={i} className="text-[11px] leading-4 text-gray-400">
              <button className="text-gray-200 hover:underline" onClick={() => onSongTitle?.(r.title, r.artist)}>{r.title}</button>
              {r.artist ? <span className="text-gray-500"> · {r.artist}</span> : null}
              <div className="text-gray-500">{r.label}: {show(r)} · {ago(r.at)}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
