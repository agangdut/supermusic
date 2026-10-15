import Link from "next/link";

import { WHO_COLORS } from "./lenses";
import { clusterName, colorFor } from "./colors";

const KIND = {
  shared: { label: "Common ground", color: WHO_COLORS.both },
  yours: { label: "Mostly yours", color: WHO_COLORS.you },
  theirs: { label: "Mostly theirs", color: WHO_COLORS.them },
};

function search(t) {
  return `https://www.youtube.com/results?search_query=${encodeURIComponent([t.artist, t.title].filter(Boolean).join(" "))}`;
}

function Bar({ g }) {
  const total = g.you + g.them + g.both || 1;
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-white/5">
      <div style={{ width: `${(g.you / total) * 100}%`, background: WHO_COLORS.you }} />
      <div style={{ width: `${(g.both / total) * 100}%`, background: WHO_COLORS.both }} />
      <div style={{ width: `${(g.them / total) * 100}%`, background: WHO_COLORS.them }} />
    </div>
  );
}

function Picks({ title, items }) {
  if (!items?.length) return null;
  return (
    <section>
      <h3 className="text-[11px] uppercase tracking-wider text-gray-500">{title}</h3>
      <div className="mt-1.5 space-y-1">
        {items.slice(0, 6).map((p) => (
          <a key={`${p.artist}|${p.title}`} href={search(p)} target="_blank" rel="noopener noreferrer"
            className="block truncate text-xs text-gray-300 hover:text-white">
            {p.title} <span className="text-gray-500">· {p.artist}{p.you_like_artist ? " (an artist you play)" : ""}</span>
          </a>
        ))}
      </div>
    </section>
  );
}

/** The Compare tab: how two libraries overlap, galaxy by galaxy. */
export default function ComparePanel({ blend, clusters, focusCluster, onFocus }) {
  const byId = Object.fromEntries((clusters || []).map((c) => [c.id, c]));
  const { counts } = blend;
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-center">
        <div className="text-4xl font-bold tabular-nums text-white">{blend.match}%</div>
        <div className="text-xs text-gray-400">taste match, by the artists you both play</div>
        <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
          {[["you", "Only you"], ["both", "Both"], ["them", "Only them"]].map(([k, label]) => (
            <div key={k}>
              <div className="text-base font-semibold tabular-nums" style={{ color: WHO_COLORS[k] }}>{counts[k].toLocaleString()}</div>
              <div className="text-gray-500">{label}</div>
            </div>
          ))}
        </div>
        {blend.top_shared_artists?.length > 0 && (
          <div className="mt-3 text-[11px] text-gray-400">You both play {blend.top_shared_artists.join(", ")}</div>
        )}
        {blend.theirs?.id && (
          <div className="mt-3 flex justify-center gap-3 text-[11px]">
            <Link href={`/?share=${encodeURIComponent(blend.theirs.id)}`} className="text-fuchsia-300 hover:underline">Open their map</Link>
            {blend.theirs.owner && <Link href={`/u/${blend.theirs.owner}`} className="text-fuchsia-300 hover:underline">Their profile</Link>}
          </div>
        )}
      </div>

      <section>
        <h3 className="text-[11px] uppercase tracking-wider text-gray-500">Galaxies</h3>
        <p className="mt-1 text-[11px] leading-5 text-gray-500">Click one to light it up. Blue is yours, pink is theirs, gold is both.</p>
        <div className="mt-2 space-y-2">
          {blend.galaxies.map((g) => {
            const c = byId[g.id];
            return (
              <button key={g.id} onClick={() => onFocus(g.id)}
                className={`block w-full rounded-xl border p-2.5 text-left transition ${focusCluster === g.id ? "border-white/25 bg-white/[0.06]" : "border-white/5 hover:border-white/15"}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: colorFor(g.id) }} />
                    <span className="truncate text-sm font-medium text-white">{clusterName(c || g)}</span>
                    <span className="truncate text-[11px] text-gray-500">{(g.label || "").split(" · ")[0]}</span>
                  </span>
                  <span className="shrink-0 rounded px-1.5 py-px text-[10px]" style={{ color: KIND[g.kind].color, border: `1px solid ${KIND[g.kind].color}55` }}>
                    {KIND[g.kind].label}
                  </span>
                </div>
                <div className="mt-2"><Bar g={g} /></div>
              </button>
            );
          })}
        </div>
      </section>

      <Picks title="From their map, for you" items={blend.for_you} />
      <Picks title="From yours, for them" items={blend.for_them} />
    </div>
  );
}

/** Shown on a compare link when we don't know your library yet. */
export function CompareGate({ signedIn, onImport, onSample, onCancel }) {
  return (
    <div className="w-full max-w-md rounded-2xl border border-fuchsia-400/25 bg-[#0b1121]/95 p-6 text-center shadow-2xl backdrop-blur">
      <div className="mx-auto flex w-fit -space-x-2">
        <span className="h-9 w-9 rounded-full" style={{ background: WHO_COLORS.you, boxShadow: `0 0 24px ${WHO_COLORS.you}` }} />
        <span className="h-9 w-9 rounded-full" style={{ background: WHO_COLORS.them, boxShadow: `0 0 24px ${WHO_COLORS.them}` }} />
      </div>
      <h2 className="mt-4 text-lg font-semibold text-white">Compare your taste</h2>
      <p className="mt-1 text-sm leading-6 text-gray-400">
        Import your Spotify or Apple Music library and we&apos;ll draw both of you on one map: the galaxies you share,
        the ones that are only yours, and songs to swap.
      </p>
      <div className="mt-5 flex flex-col gap-2">
        <button onClick={onImport} className="rounded-xl bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-4 py-2.5 text-sm font-semibold text-white">
          Import my library
        </button>
        <button onClick={onSample} className="rounded-xl border border-white/15 px-4 py-2 text-sm text-gray-200 hover:bg-white/5">
          Just try it with the sample library
        </button>
        {!signedIn && (
          <Link href="/login" className="text-xs text-gray-400 hover:text-white">Already imported on another device? Sign in</Link>
        )}
        <button onClick={onCancel} className="text-xs text-gray-500 hover:text-white">Not now</button>
      </div>
    </div>
  );
}
