import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";

import PageShell from "@/components/layout/PageShell";
import { myShares, stopSharing } from "@/components/map/ShareDialog";
import { listSharedMaps } from "@/lib/api";

const when = (s) => new Date(s * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

function MapCard({ m, onStop }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 transition hover:border-white/20">
      <Link href={`/map?share=${encodeURIComponent(m.id)}`} className="block">
        <div className="truncate font-semibold text-white">{m.title}</div>
        <div className="mt-0.5 text-xs text-gray-500">
          {[m.by || "Anonymous", m.songs != null && `${m.songs.toLocaleString()} songs`, m.created && when(m.created)].filter(Boolean).join(" · ")}
        </div>
        {m.clusters?.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {m.clusters.map((c) => (
              <span key={c} className="rounded-md border border-white/10 bg-white/5 px-1.5 py-0.5 text-[11px] text-gray-300">{c.split(" · ")[0]}</span>
            ))}
          </div>
        )}
      </Link>
      {onStop && (
        <button onClick={() => onStop(m.id)} className="mt-3 text-[11px] text-gray-500 hover:text-rose-300">Stop sharing</button>
      )}
    </div>
  );
}

export default function SharedMaps() {
  const [maps, setMaps] = useState(null);
  const [mine, setMine] = useState([]);
  const [error, setError] = useState(null);

  const refresh = () => listSharedMaps().then((r) => setMaps(r.maps)).catch((e) => setError(e.message || String(e)));
  useEffect(() => {
    setMine(myShares());
    refresh();
  }, []);

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

  return (
    <PageShell>
      <Head><title>Shared maps · SuperMusic</title></Head>
      <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">Shared maps</h1>
      <p className="mt-1 max-w-2xl text-sm text-gray-400">
        Other people&apos;s Music Maps. Open one to explore their taste, or start a radio station from any part of it.
        To share yours, open your map and press <span className="text-gray-200">Share</span>.
      </p>
      {error && <p className="mt-4 text-sm text-rose-300">{error}</p>}

      {mine.length > 0 && (
        <>
          <h2 className="mt-8 text-sm font-semibold uppercase tracking-wider text-gray-500">Shared from this browser</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {mine.map((m) => <MapCard key={m.id} m={m} onStop={stop} />)}
          </div>
        </>
      )}

      <h2 className="mt-8 text-sm font-semibold uppercase tracking-wider text-gray-500">Everyone&apos;s</h2>
      {maps === null && !error && <p className="mt-3 text-sm text-gray-500">Loading…</p>}
      {maps?.length === 0 && <p className="mt-3 text-sm text-gray-500">Nobody has listed a map yet.</p>}
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {(maps || []).map((m) => <MapCard key={m.id} m={m} />)}
      </div>
    </PageShell>
  );
}
