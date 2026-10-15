// Cards for shared maps: the picture, headline stats and an upvote button.
// Used by Explore (/maps) and profiles.
import { useState } from "react";
import Link from "next/link";

import UpvoteButton from "@/components/map/UpvoteButton";
import { sharedMapPicture } from "@/lib/api";

export const when = (s) => new Date(s * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
export const num = (n) => (n == null ? "–" : n >= 10000 ? `${(n / 1000).toFixed(n >= 100000 ? 0 : 1)}k` : n.toLocaleString());
const keyName = (k) => (/^[A-G][#b]?m$/.test(k) ? `${k.slice(0, -1)} minor` : /^[A-G][#b]?$/.test(k) ? `${k} major` : k);
export const mapUrl = (id) => `/?share=${encodeURIComponent(id)}`;

export function Picture({ id, className = "" }) {
  const [failed, setFailed] = useState(false);
  return (
    <div className={`relative overflow-hidden bg-[radial-gradient(ellipse_at_center,_#1a1440_0%,_#0b1121_55%,_#05070f_100%)] ${className}`}>
      {!failed && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={sharedMapPicture(id)} alt="" loading="lazy" onError={() => setFailed(true)}
          className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]" />
      )}
    </div>
  );
}

export function Stat({ label, value }) {
  return (
    <div className="min-w-0">
      <div className="text-base font-semibold tabular-nums text-white">{value}</div>
      <div className="truncate text-[10px] uppercase tracking-wider text-gray-500">{label}</div>
    </div>
  );
}

// The one or two facts most worth showing off for a map
export function Highlights({ s, limit = 2 }) {
  if (!s) return null;
  const items = [];
  if (s.most_loved) {
    items.push(["💗", <>Plays <b className="text-white">{s.most_loved.name}</b> {s.most_loved.lift}× more than its size</>]);
  }
  if (s.most_played) {
    items.push(["🔁", <>Most played: <b className="text-white">{s.most_played.title}</b>{s.most_played.artist ? ` by ${s.most_played.artist}` : ""} ({num(s.most_played.plays)} plays)</>]);
  }
  if (s.best_link) {
    items.push(["✦", <>Hidden link: <b className="text-white">{s.best_link.a}</b> ↔ <b className="text-white">{s.best_link.b}</b>{s.best_link.why ? ` (${s.best_link.why})` : ""}</>]);
  }
  const vibe = [s.top_key && `mostly ${keyName(s.top_key)}`, s.median_bpm && `around ${s.median_bpm} BPM`, s.top_decade && `lots of ${s.top_decade}`].filter(Boolean);
  if (vibe.length) items.push(["🎚️", <>Sounds {vibe.join(", ")}</>]);
  return (
    <ul className="space-y-1">
      {items.slice(0, limit).map(([icon, text], i) => (
        <li key={i} className="flex gap-2 text-xs leading-5 text-gray-400">
          <span className="w-4 shrink-0 text-center">{icon}</span>
          <span className="min-w-0">{text}</span>
        </li>
      ))}
    </ul>
  );
}

export function Galaxies({ s, max = 4 }) {
  if (!s?.galaxies?.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {s.galaxies.slice(0, max).map((g) => (
        <span key={g.id} title={g.label} className="flex items-center gap-1.5 rounded-md border border-white/10 bg-white/[0.04] px-1.5 py-0.5 text-[11px] text-gray-300">
          <span className="h-2 w-2 rounded-full" style={{ background: g.color, boxShadow: `0 0 6px ${g.color}` }} />
          {g.name}
          <span className="text-gray-500">{(g.label || "").split(" · ")[0]}</span>
        </span>
      ))}
    </div>
  );
}

function Byline({ m }) {
  return (
    <div className="truncate text-xs text-gray-500">
      {[m.by || "Anonymous", m.created && when(m.created)].filter(Boolean).join(" · ")}
    </div>
  );
}

// The most upvoted map, big
export function Featured({ m }) {
  const s = m.showcase || {};
  return (
    <div className="group grid overflow-hidden rounded-2xl border border-fuchsia-400/20 bg-white/[0.03] transition hover:border-fuchsia-400/40 lg:grid-cols-[1.4fr_1fr]">
      <Link href={mapUrl(m.id)} className="block"><Picture id={m.id} className="aspect-video h-full lg:aspect-auto lg:min-h-[320px]" /></Link>
      <div className="flex flex-col gap-4 p-5">
        <div className="flex items-start justify-between gap-3">
          <Link href={mapUrl(m.id)} className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-fuchsia-300">Top map</div>
            <div className="mt-1 truncate text-xl font-bold text-white">{m.title}</div>
            <Byline m={m} />
          </Link>
          <UpvoteButton id={m.id} votes={m.votes} voted={m.voted} size="lg" />
        </div>
        <div className="grid grid-cols-4 gap-3">
          <Stat label="Songs" value={num(s.songs ?? m.songs)} />
          <Stat label="Artists" value={num(s.artists)} />
          <Stat label="Galaxies" value={num(s.clusters)} />
          <Stat label={s.plays ? "Plays" : "Hidden links"} value={num(s.plays ?? s.hidden_links)} />
        </div>
        <Galaxies s={s} max={5} />
        <Highlights s={s} limit={4} />
        <Link href={mapUrl(m.id)} className="mt-auto text-sm font-medium text-fuchsia-200 hover:text-white">Explore this map →</Link>
      </div>
    </div>
  );
}

export function MapCard({ m, onStop }) {
  const s = m.showcase || {};
  return (
    <div className="group flex flex-col overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03] transition hover:-translate-y-0.5 hover:border-white/25">
      <div className="relative">
        <Link href={mapUrl(m.id)} className="block"><Picture id={m.id} className="aspect-video" /></Link>
        <span className="pointer-events-none absolute left-2 top-2 rounded-md bg-black/50 px-1.5 py-0.5 text-[11px] text-gray-200 backdrop-blur">
          {num(s.songs ?? m.songs)} songs
        </span>
        {m.votes != null && (
          <span className="absolute right-2 top-2"><UpvoteButton id={m.id} votes={m.votes} voted={m.voted} /></span>
        )}
      </div>
      <Link href={mapUrl(m.id)} className="flex flex-1 flex-col gap-3 p-4">
        <div className="min-w-0">
          <div className="truncate font-semibold text-white">{m.title}</div>
          <Byline m={m} />
        </div>
        {m.showcase && (
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Artists" value={num(s.artists)} />
            <Stat label="Galaxies" value={num(s.clusters)} />
            <Stat label="Hidden links" value={num(s.hidden_links)} />
          </div>
        )}
        <Galaxies s={s} max={3} />
        <Highlights s={s} />
      </Link>
      {onStop && (
        <button onClick={() => onStop(m.id)} className="border-t border-white/5 px-4 py-2 text-left text-[11px] text-gray-500 hover:text-rose-300">
          Stop sharing
        </button>
      )}
    </div>
  );
}

