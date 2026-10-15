// The "Atlas": every cluster as a card with the music inside it (artists, typical songs,
// sub-groups), instead of a name and a bar. Made for big libraries, where the 3D view
// alone is a cloud of 20,000 stars.
import { clusterName, colorFor, galaxyTitle } from "./colors";

const pct = (v) => `${v < 0.01 && v > 0 ? "<1" : Math.round(v * 100)}%`;

function Song({ t, onSelect }) {
  if (!t) return null;
  return (
    <button onClick={() => onSelect(t.id)} className="group block w-full truncate text-left text-xs">
      <span className="text-gray-200 group-hover:text-white">{t.title}</span>
      {t.artist && <span className="text-gray-500"> · {t.artist}</span>}
    </button>
  );
}

function ClusterCard({ c, byId, maxSize, onFocus, onSelect, focused }) {
  const color = colorFor(c.id);
  const chips = [
    c.top_keys?.[0] && c.top_keys[0].share >= 0.2 && `${c.top_keys[0].name} (${pct(c.top_keys[0].share)})`,
    c.bpm_range && `${c.bpm_range[0]}–${c.bpm_range[1]} BPM`,
    c.years && (c.years[0] === c.years[1] ? `${c.years[0]}` : `${c.years[0]}–${c.years[1]}`),
    ...(c.mood || []),
  ].filter(Boolean);
  return (
    <div className={`flex flex-col rounded-xl border p-4 transition ${focused ? "border-white/30 bg-white/[0.06]" : "border-white/10 bg-white/[0.02] hover:border-white/20"}`}
      style={{ boxShadow: focused ? `0 0 24px ${color}33` : undefined }}>
      <button onClick={() => onFocus(c.id)} className="text-left">
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: color, boxShadow: `0 0 12px ${color}` }} />
            <span className="min-w-0">
              <span className="block text-sm font-semibold leading-snug text-white" title={galaxyTitle(c)}>{clusterName(c)}</span>
              {c.name && <span className="block truncate text-[11px] text-gray-400">{c.label.split(" · ")[0]}</span>}
            </span>
          </div>
          <span className="shrink-0 text-xs tabular-nums text-gray-400">{c.size.toLocaleString()} songs</span>
        </div>
        {/* Size of the library vs share of the listening, on one scale */}
        <div className="mt-3 space-y-1">
          <div className="h-1.5 rounded-r bg-slate-500" style={{ width: `${Math.max(2, (c.size / maxSize) * 100)}%` }} title="Size of this cluster" />
          {c.listening_share != null && (
            <div className="text-[11px] text-gray-400">
              <span className="font-medium text-gray-200">{pct(c.listening_share)}</span> of your plays
              {c.lift != null && (c.lift >= 1.15 ? <span className="text-fuchsia-300"> · {c.lift}× its size</span> : c.lift <= 0.85 ? <span className="text-gray-500"> · {c.lift}× its size</span> : null)}
            </div>
          )}
        </div>
      </button>
      {chips.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {chips.map((x) => <span key={x} className="rounded-md border border-white/10 px-1.5 py-0.5 text-[10px] text-gray-300">{x}</span>)}
        </div>
      )}
      {c.top_artists?.length > 0 && (
        <p className="mt-3 text-xs leading-5 text-gray-400">
          <span className="text-gray-500">Artists: </span>
          {c.top_artists.map((a) => a.name).join(", ")}
        </p>
      )}
      {c.top_tracks?.length > 0 && (
        <div className="mt-2">
          <div className="text-[10px] uppercase tracking-wider text-gray-500">{c.listening_share != null ? "Most played" : "Most typical"}</div>
          <div className="mt-1 space-y-0.5">{c.top_tracks.slice(0, 4).map((id) => <Song key={id} t={byId[id]} onSelect={onSelect} />)}</div>
        </div>
      )}
      {c.subgroups?.length > 1 && (
        <div className="mt-3 border-t border-white/5 pt-2">
          <div className="text-[10px] uppercase tracking-wider text-gray-500">Inside</div>
          <div className="mt-1 space-y-1.5">
            {c.subgroups.map((g, i) => (
              <div key={i} className="text-xs">
                <div className="flex justify-between gap-2">
                  <span className="truncate text-gray-200">{g.label}</span>
                  <span className="shrink-0 tabular-nums text-gray-500">{g.size.toLocaleString()}{g.listening_share != null ? ` · ${pct(g.listening_share)} of plays` : ""}</span>
                </div>
                <div className="truncate text-[11px] text-gray-500">
                  {g.top_tracks.map((id) => byId[id]).filter(Boolean).map((t, k) => (
                    <button key={t.id} onClick={() => onSelect(t.id)} className="hover:text-gray-200">{k ? ", " : "e.g. "}{t.title}</button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function ClusterAtlas({ clusters, byId, focusCluster, onFocus, onSelect }) {
  if (!clusters?.length) return null;
  const maxSize = Math.max(...clusters.map((c) => c.size));
  const withPlays = clusters.some((c) => c.listening_share != null);
  // Most-played first when there is listening data, otherwise biggest first
  const sorted = [...clusters].sort((a, b) => (withPlays ? (b.listening_share ?? 0) - (a.listening_share ?? 0) : b.size - a.size));
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {sorted.map((c) => (
        <ClusterCard key={c.id} c={c} byId={byId} maxSize={maxSize} focused={focusCluster === c.id}
          onFocus={onFocus} onSelect={onSelect} />
      ))}
    </div>
  );
}
