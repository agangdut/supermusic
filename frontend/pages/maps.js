import { useCallback, useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";

import PageShell from "@/components/layout/PageShell";
import { myShares, stopSharing } from "@/components/map/ShareDialog";
import UpvoteButton from "@/components/map/UpvoteButton";
import { listSharedMaps, sharedMapPicture } from "@/lib/api";

const when = (s) => new Date(s * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
const num = (n) => (n == null ? "–" : n >= 10000 ? `${(n / 1000).toFixed(n >= 100000 ? 0 : 1)}k` : n.toLocaleString());
const keyName = (k) => (/^[A-G][#b]?m$/.test(k) ? `${k.slice(0, -1)} minor` : /^[A-G][#b]?$/.test(k) ? `${k} major` : k);
const mapUrl = (id) => `/map?share=${encodeURIComponent(id)}`;

function Picture({ id, className = "" }) {
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

function Stat({ label, value }) {
  return (
    <div className="min-w-0">
      <div className="text-base font-semibold tabular-nums text-white">{value}</div>
      <div className="truncate text-[10px] uppercase tracking-wider text-gray-500">{label}</div>
    </div>
  );
}

// The one or two facts most worth showing off for a map
function Highlights({ s, limit = 2 }) {
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

function Galaxies({ s, max = 4 }) {
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
function Featured({ m }) {
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

function MapCard({ m, onStop }) {
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

const SORTS = [
  { id: "top", label: "Most upvoted" },
  { id: "new", label: "Newest" },
];

export default function SharedMaps() {
  const [sort, setSort] = useState("top");
  const [maps, setMaps] = useState(null);
  const [mine, setMine] = useState([]);
  const [error, setError] = useState(null);

  const refresh = useCallback(
    () => listSharedMaps(sort).then((r) => setMaps(r.maps)).catch((e) => setError(e.message || String(e))),
    [sort],
  );
  useEffect(() => { setMine(myShares()); }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const stop = async (id) => {
    if (!window.confirm("Stop sharing this map? The link will stop working for everyone.")) return;
    try {
      await stopSharing(id);
      setMine(myShares());
      refresh();
    } catch (e) {
      setError(e.message || String(e));
    }
  };

  // Listed maps already carry their stats and votes; maps shared link-only show what this browser remembers
  const byId = Object.fromEntries((maps || []).map((m) => [m.id, m]));
  const featured = sort === "top" && maps?.length > 2 && maps[0].votes > 0 ? maps[0] : null;
  const rest = featured ? maps.slice(1) : maps || [];

  return (
    <PageShell>
      <Head><title>Shared maps · SuperMusic</title></Head>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-2xl">
          <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">Shared maps</h1>
          <p className="mt-1 text-sm text-gray-400">
            Other people&apos;s music, drawn as galaxies. Open one to explore their taste or start a radio station from it,
            and upvote the ones you like.
          </p>
        </div>
        <Link href="/map" className="rounded-xl bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-fuchsia-600/20 hover:brightness-110">
          Share your map
        </Link>
      </div>
      {error && <p className="mt-4 text-sm text-rose-300">{error}</p>}

      <div className="mt-6 flex gap-1">
        {SORTS.map((s) => (
          <button key={s.id} onClick={() => setSort(s.id)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${sort === s.id ? "bg-white/10 text-white" : "text-gray-400 hover:text-gray-200"}`}>
            {s.label}
          </button>
        ))}
      </div>

      {maps === null && !error && <p className="mt-4 text-sm text-gray-500">Loading…</p>}
      {maps?.length === 0 && (
        <div className="mt-4 rounded-2xl border border-dashed border-white/15 p-8 text-center text-sm text-gray-400">
          Nobody has listed a map yet. Open your <Link href="/map" className="text-fuchsia-300 hover:underline">Music Map</Link>,
          press Share and tick &ldquo;List it on Shared maps&rdquo; to be the first.
        </div>
      )}
      {featured && <div className="mt-4"><Featured m={featured} /></div>}
      <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {rest.map((m) => <MapCard key={m.id} m={m} />)}
      </div>

      {mine.length > 0 && (
        <>
          <h2 className="mt-10 text-sm font-semibold uppercase tracking-wider text-gray-500">Shared from this browser</h2>
          <div className="mt-3 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {mine.map((m) => <MapCard key={m.id} m={{ ...m, ...byId[m.id] }} onStop={stop} />)}
          </div>
        </>
      )}
    </PageShell>
  );
}
