import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";

import PageShell from "@/components/layout/PageShell";
import { clusterName, colorFor } from "@/components/map/colors";
import { ago } from "@/components/social/EventLine";
import { addAtlasPin, atlasMine, atlasPins, atlasSong, deleteAtlasPin, getAtlas, myMap } from "@/lib/api";
import { listenerId } from "@/utils/fetcher";
import { useAuth } from "@/lib/auth";

const Graph3D = dynamic(() => import("@/components/map/Graph3D"), { ssr: false });

const TABS = [
  { id: "galaxies", label: "Galaxies" },
  { id: "notes", label: "Notes" },
  { id: "artists", label: "New from artists" },
];

function SongCard({ t, onClose }) {
  const { user } = useAuth();
  const [info, setInfo] = useState(null);
  const [text, setText] = useState("");
  const [error, setError] = useState(null);
  const load = () => atlasSong(t.song_key).then(setInfo).catch(() => setInfo({ maps: [], pins: [] }));
  useEffect(() => { setInfo(null); setText(""); setError(null); load(); }, [t.song_key]); // eslint-disable-line react-hooks/exhaustive-deps
  const me = user ? `user:${user.username}` : `anon:${listenerId()}`;
  const pin = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      await addAtlasPin({ song_key: t.song_key, text, title: t.title });
      setText("");
      load();
    } catch (err) {
      setError(err.message || String(err));
    }
  };
  return (
    <div className="absolute inset-x-3 bottom-16 z-30 max-h-[50%] overflow-y-auto rounded-2xl border border-white/10 bg-[#0b1121]/90 p-4 backdrop-blur md:inset-x-auto md:bottom-3 md:left-3 md:max-h-[calc(100%-24px)] md:w-[340px]">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-semibold text-white">{t.title}</div>
          <div className="truncate text-xs text-gray-400">{[t.artist, t.genre].filter(Boolean).join(" · ")}</div>
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-white" aria-label="Close">✕</button>
      </div>
      <div className="mt-2 text-xs text-gray-400">In <b className="text-gray-200">{t.listeners}</b> public librar{t.listeners === 1 ? "y" : "ies"}</div>
      {info?.maps?.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {info.maps.slice(0, 8).map((m) => (
            <Link key={m.id} href={`/s/${m.id}`} className="rounded-md border border-white/10 px-1.5 py-0.5 text-[11px] text-gray-300 hover:text-white">
              {m.title}{m.by ? ` · ${m.by}` : ""}
            </Link>
          ))}
        </div>
      )}
      <div className="mt-3 text-[11px] uppercase tracking-wider text-gray-500">Notes</div>
      {info?.pins?.length === 0 && <p className="mt-1 text-xs text-gray-500">No notes yet. Leave the first.</p>}
      <div className="mt-1 space-y-2">
        {info?.pins?.map((p) => (
          <div key={p.id} className="rounded-lg bg-white/[0.04] px-2.5 py-1.5 text-xs">
            <div className="text-gray-200">{p.text}</div>
            <div className="mt-0.5 flex justify-between text-[10px] text-gray-500">
              <span>{p.username ? <Link href={`/u/${p.username}`} className="hover:text-gray-300">{p.author}</Link> : p.author} · {ago(p.at)}</span>
              {p.voter === me && <button onClick={() => deleteAtlasPin(p.id).then(load)} className="hover:text-rose-300">remove</button>}
            </div>
          </div>
        ))}
      </div>
      <form onSubmit={pin} className="mt-2 flex gap-2">
        <input value={text} onChange={(e) => setText(e.target.value)} maxLength={200} placeholder="Pin a note: a memory, a mix tip…"
          className="min-w-0 flex-1 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-white placeholder:text-gray-500 focus:border-fuchsia-400/50 focus:outline-none" />
        <button disabled={!text.trim()} className="rounded-lg bg-white/10 px-3 text-xs text-white hover:bg-white/15 disabled:opacity-40">Pin</button>
      </form>
      {error && <p className="mt-1 text-xs text-rose-300">{error}</p>}
    </div>
  );
}

export default function Atlas() {
  const router = useRouter();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("galaxies");
  const [selectedId, setSelectedId] = useState(null);
  const [clusterFocus, setClusterFocus] = useState(null);
  const [mine, setMine] = useState(null); // { which: "mine" | "sample", ids: Set of atlas ids, songs, title }
  const { user } = useAuth();
  const [myMapKnown, setMyMapKnown] = useState(null);
  useEffect(() => { setMyMapKnown(myMap()); }, []);
  const [pins, setPins] = useState(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  useEffect(() => { getAtlas().then(setData).catch((e) => setError(e.message || String(e))); }, []);
  useEffect(() => { if (tab === "notes" && !pins) atlasPins().then((r) => setPins(r.pins)).catch(() => setPins([])); }, [tab, pins]);

  // /atlas?track=<id>: an artist's track, shown in its galaxy
  useEffect(() => {
    const id = router.query.track;
    if (!data || typeof id !== "string") return;
    const t = data.artist_tracks?.find((x) => x.id === id);
    if (t) { setTab("artists"); setClusterFocus(t.galaxy?.id ?? null); }
  }, [data, router.query.track]);

  const byKey = useMemo(() => Object.fromEntries((data?.tracks || []).map((t) => [t.song_key, t])), [data]);
  const selected = selectedId != null ? data?.tracks[selectedId] : null;
  const focusIds = useMemo(() => {
    if (!data) return null;
    if (selectedId != null) {
      const s = new Set([selectedId]);
      data.edges.forEach((e) => { if (e.source === selectedId) s.add(e.target); if (e.target === selectedId) s.add(e.source); });
      return s;
    }
    if (clusterFocus != null) return new Set(data.tracks.filter((t) => t.cluster === clusterFocus).map((t) => t.id));
    if (mine?.ids.size) return mine.ids;
    return null;
  }, [data, selectedId, clusterFocus, mine]);

  // Light up a library's songs: the sample, or the one you imported on the map
  const lightUp = async (which) => {
    if (mine?.which === which) { setMine(null); return; }
    const m = myMap();
    const src = which === "sample" ? { sample: true } : m?.csv_path ? { csv_path: m.csv_path } : { account: true };
    try {
      const r = await atlasMine(src);
      setMine({ which, ids: new Set(r.ids), songs: r.songs, title: which === "sample" ? "the sample library" : m?.title || user?.library_title || "your map" });
      setSelectedId(null);
      setClusterFocus(null);
    } catch (e) {
      setError(e.message || String(e));
    }
  };
  const hasMine = !!(myMapKnown?.csv_path || user?.has_library);
  const mineGalaxies = useMemo(() => {
    if (!mine || !data) return [];
    const counts = new Map();
    data.tracks.forEach((t) => { if (mine.ids.has(t.id)) counts.set(t.cluster, (counts.get(t.cluster) || 0) + 1); });
    return [...counts].sort((a, b) => b[1] - a[1]).slice(0, 3)
      .map(([cid, n]) => ({ n, name: clusterName(data.clusters.find((c) => c.id === cid) || {}) || "a galaxy" }));
  }, [mine, data]);

  const empty = data && !data.tracks?.length;
  return (
    <PageShell bleed>
      <Head><title>Community atlas · SuperMusic</title></Head>
      <section className="relative h-[calc(100svh-7rem)] min-h-[460px] overflow-hidden bg-[radial-gradient(ellipse_at_center,_#1a1440_0%,_#0b1121_55%,_#05070f_100%)] md:h-[calc(100vh-3.5rem)]">
        {data && !empty && (
          <Graph3D data={data} selectedId={selectedId} focusIds={focusIds} highlightIds={mine?.ids} focusCluster={clusterFocus} picks={[]} mode="clusters"
            onSelect={(id) => { setSelectedId(id); if (id != null) { setClusterFocus(null); setSheetOpen(false); } }} />
        )}
        {!data && !error && <div className="absolute inset-0 grid place-items-center text-sm text-gray-400">Drawing everyone&apos;s music…</div>}
        {empty && (
          <div className="absolute inset-0 grid place-items-center p-6 text-center">
            <div className="max-w-md">
              <div className="text-lg font-semibold text-white">The atlas is waiting for its first maps</div>
              <p className="mt-2 text-sm text-gray-400">It&apos;s drawn from every library people list publicly. Share yours with &ldquo;List it&rdquo; ticked to put your songs on it.</p>
              <Link href="/" className="mt-4 inline-block rounded-xl bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white">Open your map</Link>
            </div>
          </div>
        )}

        <div className="absolute left-3 top-3 z-20 max-w-[calc(100%-24px)] md:max-w-[480px]">
          <div className="rounded-2xl border border-white/10 bg-[#0b1121]/70 px-4 py-3 backdrop-blur-md">
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-fuchsia-300/90">Community atlas</div>
            <h1 className="mt-0.5 text-lg font-bold text-white md:text-2xl">Everyone&apos;s music, one universe</h1>
            {data && !empty && (
              <p className="mt-0.5 text-xs text-gray-400">
                {data.tracks.length.toLocaleString()} songs from {data.meta.maps} public librar{data.meta.maps === 1 ? "y" : "ies"}. Brighter stars are in more libraries.
                {data.meta.refreshing ? " Updating with new maps…" : ""}
              </p>
            )}
            {data && !empty && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                <span className="self-center pr-1 text-[11px] text-gray-400">Light up</span>
                {[["mine", "My map"], ["sample", "The sample"]].map(([which, label]) => (
                  <button key={which} onClick={() => lightUp(which)} disabled={which === "mine" && !hasMine}
                    title={which === "mine" && !hasMine ? "Import your library on the Map first" : undefined}
                    className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                      mine?.which === which ? "bg-yellow-300 text-[#0b1121] shadow-[0_0_18px_rgba(253,224,71,0.55)]"
                        : which === "mine" && !hasMine ? "cursor-not-allowed border border-white/10 text-gray-500"
                          : "border border-yellow-300/40 text-yellow-100 hover:bg-yellow-300/10"}`}>
                    {mine?.which === which ? `✓ ${label}` : label}
                  </button>
                ))}
                <Link href="/artists" className="rounded-lg border border-white/15 px-3 py-1.5 text-xs text-gray-200 hover:bg-white/10">Add your track</Link>
              </div>
            )}
            {mine && (
              <div className="mt-2 flex items-start gap-2 rounded-xl border border-yellow-300/30 bg-yellow-300/[0.07] px-3 py-2 text-xs text-yellow-50">
                <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-yellow-300 shadow-[0_0_10px_#fde047]" />
                <span className="min-w-0 flex-1">
                  {mine.ids.size
                    ? <><b>{mine.ids.size}</b> songs from {mine.title} are on the atlas, glowing gold{mineGalaxies.length ? <>, mostly in {mineGalaxies.map((g) => g.name).join(", ")}</> : null}.</>
                    : <>None of the songs from {mine.title} are on the atlas yet. Share your map with &ldquo;List it&rdquo; ticked to add them.</>}
                </span>
                <button onClick={() => setMine(null)} className="shrink-0 text-yellow-200/70 hover:text-white">Clear</button>
              </div>
            )}
          </div>
        </div>
        {error && <div className="absolute left-1/2 top-3 z-30 w-[min(520px,calc(100%-24px))] -translate-x-1/2 rounded-xl border border-red-500/30 bg-red-950/80 px-4 py-3 text-sm text-red-200">{error}</div>}

        {selected && <SongCard t={selected} onClose={() => setSelectedId(null)} />}

        {data && !empty && (
          <aside className={`absolute inset-x-0 bottom-0 z-20 flex flex-col rounded-t-2xl border border-white/10 bg-[#0b1121]/90 backdrop-blur-md transition-[height] duration-300 md:inset-x-auto md:bottom-3 md:right-3 md:top-3 md:h-auto md:w-[340px] md:rounded-2xl ${sheetOpen ? "h-[60%]" : "h-[52px]"}`}>
            <button onClick={() => setSheetOpen((o) => !o)} className="flex justify-center pt-1.5 md:hidden" aria-label="Toggle panel">
              <span className="h-1 w-10 rounded-full bg-white/25" />
            </button>
            <div className="flex gap-1 border-b border-white/10 p-1.5">
              {TABS.map((t) => (
                <button key={t.id} onClick={() => { setTab(t.id); setSheetOpen(true); }}
                  className={`shrink-0 rounded-lg px-2.5 py-1.5 text-xs font-medium ${tab === t.id ? "bg-white/10 text-white" : "text-gray-400 hover:text-gray-200"}`}>
                  {t.label}
                </button>
              ))}
            </div>
            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
              {tab === "galaxies" && data.clusters.map((c) => (
                <button key={c.id} onClick={() => { setSelectedId(null); setClusterFocus(clusterFocus === c.id ? null : c.id); }}
                  className={`block w-full rounded-xl border p-2.5 text-left ${clusterFocus === c.id ? "border-white/25 bg-white/[0.06]" : "border-white/5 hover:border-white/15"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: colorFor(c.id), boxShadow: `0 0 10px ${colorFor(c.id)}` }} />
                      <span className="truncate text-sm font-medium text-white">{clusterName(c)}</span>
                    </span>
                    <span className="text-xs text-gray-500">{c.size}</span>
                  </div>
                  <div className="mt-1 truncate text-[11px] text-gray-400">{c.label}</div>
                  {c.top_artists?.length > 0 && <div className="truncate text-[11px] text-gray-500">{c.top_artists.slice(0, 3).map((a) => a.name).join(", ")}</div>}
                </button>
              ))}
              {tab === "notes" && (
                <>
                  {pins?.length === 0 && <p className="text-xs text-gray-500">No notes yet. Click a star and pin one.</p>}
                  {pins?.map((p) => {
                    const t = byKey[p.song_key];
                    return (
                      <button key={p.id} onClick={() => t && setSelectedId(t.id)} className="block w-full rounded-xl border border-white/5 p-2.5 text-left hover:border-white/15">
                        <div className="text-xs text-gray-200">&ldquo;{p.text}&rdquo;</div>
                        <div className="mt-1 truncate text-[11px] text-gray-500">{t ? `${t.title} · ${t.artist || ""}` : "a song no longer on the atlas"} · {p.author}</div>
                      </button>
                    );
                  })}
                </>
              )}
              {tab === "artists" && (
                <>
                  <p className="text-[11px] leading-5 text-gray-500">Tracks artists uploaded, placed next to the songs they sound like. Click one to light up its galaxy.</p>
                  {data.artist_tracks?.length === 0 && <p className="text-xs text-gray-500">None yet. <Link href="/artists" className="text-fuchsia-300 hover:underline">Add yours</Link>.</p>}
                  {data.artist_tracks?.map((t) => (
                    <button key={t.id} onClick={() => { setSelectedId(null); setClusterFocus(t.galaxy?.id ?? null); }}
                      className={`block w-full rounded-xl border p-2.5 text-left ${router.query.track === t.id ? "border-fuchsia-400/40" : "border-white/5 hover:border-white/15"}`}>
                      <div className="truncate text-sm text-white">{t.title}</div>
                      <div className="truncate text-[11px] text-gray-500">
                        {t.artist || t.owner} · lands in <span style={{ color: colorFor(t.galaxy?.id) }}>{t.galaxy?.name}</span>
                      </div>
                      {t.owner && <Link href={`/u/${t.owner}`} onClick={(e) => e.stopPropagation()} className="text-[11px] text-fuchsia-300 hover:underline">@{t.owner}</Link>}
                    </button>
                  ))}
                </>
              )}
            </div>
          </aside>
        )}
      </section>
    </PageShell>
  );
}
