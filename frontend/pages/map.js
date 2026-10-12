import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Head from "next/head";

import PageShell from "@/components/layout/PageShell";
import { buildMap, getImport, getMapEstimate, importLibrary } from "@/lib/api";
import { colorFor } from "@/components/map/colors";
import ImportProgress, { BuildProgress } from "@/components/map/ImportProgress";

const Graph3D = dynamic(() => import("@/components/map/Graph3D"), {
  ssr: false,
  loading: () => <Centered>Warming up the 3D view…</Centered>,
});

const ASPECTS = [
  { key: "key", label: "Key", hint: "Harmonic keys (Camelot wheel)" },
  { key: "tempo", label: "Tempo", hint: "BPM, on a log scale" },
  { key: "genre", label: "Genre", hint: "Genre and style tags" },
  { key: "mood", label: "Mood", hint: "Energy, valence, danceability…" },
  { key: "artist", label: "Artist", hint: "Same artist pulls together" },
];

const TABS = [
  { id: "clusters", label: "Clusters" },
  { id: "hidden", label: "Hidden links" },
  { id: "picks", label: "For you" },
];

function Centered({ children }) {
  return <div className="absolute inset-0 grid place-items-center text-sm text-gray-400">{children}</div>;
}

function SignalBar({ value, color }) {
  return (
    <div className="h-1.5 w-full rounded-full bg-white/5">
      <div
        className="h-1.5 rounded-full"
        style={{ width: `${Math.max(4, value * 100)}%`, background: color, boxShadow: `0 0 10px ${color}` }}
      />
    </div>
  );
}

function Chip({ children }) {
  return <span className="rounded-md border border-white/10 bg-white/5 px-1.5 py-0.5 text-[11px] text-gray-300">{children}</span>;
}

function TrackLine({ t, onClick, sub }) {
  if (!t) return null;
  return (
    <button onClick={onClick} className="group flex w-full items-start gap-2 text-left">
      <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: colorFor(t.cluster), boxShadow: `0 0 8px ${colorFor(t.cluster)}` }} />
      <span className="min-w-0">
        <span className="block truncate text-sm text-gray-100 group-hover:text-white">{t.title}</span>
        <span className="block truncate text-xs text-gray-500">
          {sub ?? [t.artist, t.genre, t.key, t.bpm && `${Math.round(t.bpm)} BPM`].filter(Boolean).join(" · ")}
        </span>
      </span>
    </button>
  );
}

export default function MapPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [source, setSource] = useState({ sample: true });
  const [weights, setWeights] = useState({ key: 1, tempo: 1, genre: 1, mood: 1, artist: 0.5 });
  const [tab, setTab] = useState("clusters");
  const [selectedId, setSelectedId] = useState(null);
  const [clusterFocus, setClusterFocus] = useState(null);
  const fileRef = useRef();
  const requestRef = useRef(0);
  const startedRef = useRef(false);

  const [buildEstimate, setBuildEstimate] = useState(null); // seconds, when the track count is known

  const load = useCallback(async (src, w, tracks) => {
    const req = ++requestRef.current;
    setLoading(true);
    setError(null);
    setBuildEstimate(null);
    if (tracks) getMapEstimate(tracks).then((e) => req === requestRef.current && setBuildEstimate(e)).catch(() => {});
    try {
      const res = await buildMap({ ...src, weights: w });
      if (req !== requestRef.current) return; // a newer map was requested meanwhile
      setData(res);
      setSelectedId(null);
      setClusterFocus(null);
      setTab(res.recommendations?.length ? "picks" : "clusters");
    } catch (e) {
      if (req === requestRef.current) setError(e.message || String(e));
    } finally {
      if (req === requestRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (startedRef.current) return; // React strict mode runs effects twice in dev
    startedRef.current = true;
    load({ sample: true }, weights);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [pending, setPending] = useState(null); // files picked, waiting for "Build my map"
  const [enrichOnline, setEnrichOnline] = useState(true);
  const [importJob, setImportJob] = useState(null);
  const [uploading, setUploading] = useState(0); // number of files being sent
  const [lastWarning, setLastWarning] = useState(null); // e.g. online lookups were skipped

  const onFile = (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (files.length) {
      setPending(files);
      setError(null);
    }
  };

  const runImport = async () => {
    const files = pending;
    setPending(null);
    setError(null);
    setLoading(true);
    setUploading(files.length);
    setLastWarning(null);
    try {
      let job = await importLibrary(files, { enrich: enrichOnline });
      setUploading(0);
      setImportJob(job);
      let misses = 0;
      while (job.status === "running") {
        await new Promise((r) => setTimeout(r, 1000));
        try {
          job = await getImport(job.id);
          misses = 0;
        } catch (err) {
          // A lost import (server restarted) is final; a dropped poll is not
          if (/no longer running/.test(err.message || "") || ++misses >= 5) throw err;
          continue;
        }
        setImportJob(job);
      }
      if (job.status !== "done") throw new Error(job.error || "Import failed");
      setLastWarning(job.warning || null);
      requestRef.current += 1; // anything still loading is now stale
      setData(job.result);
      setSelectedId(null);
      setClusterFocus(null);
      setTab(job.result.recommendations?.length ? "picks" : "clusters");
      setSource({ csv_path: job.result.meta.library_csv }); // so Remap works on the imported library
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setUploading(0);
      setImportJob(null);
      setLoading(false);
    }
  };

  const byId = useMemo(() => Object.fromEntries((data?.tracks || []).map((t) => [t.id, t])), [data]);
  const clusterById = useMemo(() => Object.fromEntries((data?.clusters || []).map((c) => [c.id, c])), [data]);

  // Which nodes stay bright: a selected track and its links, a cluster, or a tab's subset
  const focusIds = useMemo(() => {
    if (!data) return null;
    if (selectedId != null) {
      const s = new Set([selectedId]);
      for (const e of data.edges) {
        if (e.source === selectedId) s.add(e.target);
        if (e.target === selectedId) s.add(e.source);
      }
      return s;
    }
    if (clusterFocus != null) return new Set(data.tracks.filter((t) => t.cluster === clusterFocus).map((t) => t.id));
    if (tab === "hidden") return new Set(data.hidden_connections.flatMap((h) => [h.source, h.target]));
    if (tab === "picks" && data.recommendations.length) {
      const s = new Set();
      data.recommendations.forEach((r) => { s.add(r.id); s.add(r.because_you_play); });
      return s;
    }
    return null;
  }, [data, selectedId, clusterFocus, tab]);

  const selected = selectedId != null ? byId[selectedId] : null;
  const selectedLinks = useMemo(() => {
    if (!data || selectedId == null) return [];
    return data.edges
      .filter((e) => e.source === selectedId || e.target === selectedId)
      .map((e) => ({ ...e, other: byId[e.source === selectedId ? e.target : e.source] }))
      .sort((a, b) => (b.kind === "hidden") - (a.kind === "hidden") || b.strength - a.strength);
  }, [data, selectedId, byId]);

  const picks = useMemo(() => (data?.recommendations || []).map((r) => r.id), [data]);
  const hasListening = data?.meta?.has_listening_data;

  return (
    <PageShell>
      <Head>
        <title>Music Map · SuperMusic</title>
      </Head>

      {/* Header */}
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-2xl">
          <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
            Music Map
            <span className="ml-2 align-middle text-xs font-medium text-fuchsia-300/80">beta</span>
          </h1>
          <p className="mt-1 text-sm text-gray-400">
            Every star is a track. Tracks that sound alike sit together, bright clusters are what you play most,
            and <span className="text-fuchsia-300">pink threads</span> connect songs from different worlds that would mix well.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input ref={fileRef} type="file" multiple accept=".csv,.json,.txt" onChange={onFile} className="hidden" />
          <button
            onClick={() => fileRef.current?.click()}
            className="rounded-xl bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-fuchsia-600/20 hover:brightness-110"
          >
            Import Spotify / Apple Music
          </button>
          <button
            onClick={() => { setSource({ sample: true }); load({ sample: true }, weights); }}
            className="rounded-xl border border-white/15 px-4 py-2 text-sm text-gray-200 hover:bg-white/5"
          >
            Use sample library
          </button>
          <a href="/data/sample_library.csv" download className="px-2 text-xs text-gray-400 underline-offset-2 hover:text-gray-200 hover:underline">
            CSV template
          </a>
        </div>
      </div>

      {pending && (
        <div className="mb-4 rounded-xl border border-fuchsia-400/20 bg-fuchsia-400/[0.04] p-4">
          <div className="text-sm font-medium text-white">Ready to import {pending.length} file{pending.length > 1 ? "s" : ""}</div>
          <ul className="mt-1 text-xs text-gray-400">
            {pending.map((f) => <li key={f.name}>• {f.name}</li>)}
          </ul>
          <p className="mt-2 text-[11px] leading-5 text-gray-500">
            Works with Exportify playlist CSVs, Spotify&apos;s account data export (StreamingHistory / Streaming_History_Audio JSON),
            Apple Music&apos;s privacy export (Play Activity, Track Play History, Library Tracks), the Music app&apos;s
            File › Library › Export Playlist text file, or any CSV with title and artist columns. Pick several at once to combine
            your library with your listening history.
          </p>
          <label className="mt-3 flex items-start gap-2 text-xs text-gray-300">
            <input type="checkbox" checked={enrichOnline} onChange={(e) => setEnrichOnline(e.target.checked)} className="mt-0.5 accent-fuchsia-500" />
            <span>
              Look up genre, tempo, key and energy online. Song titles and artists are sent to MusicBrainz and Deezer (and Last.fm if a key is set up), and each song&apos;s
              30-second preview is analysed on this computer. Needed for listening histories, which don&apos;t include any of that.
            </span>
          </label>
          <div className="mt-3 flex gap-2">
            <button onClick={runImport} className="rounded-lg bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-3 py-1.5 text-xs font-semibold text-white">Build my map</button>
            <button onClick={() => setPending(null)} className="rounded-lg px-3 py-1.5 text-xs text-gray-400 hover:text-white">Cancel</button>
          </div>
        </div>
      )}

      {(uploading > 0 || importJob) && (
        <ImportProgress job={importJob} uploading={uploading > 0} fileCount={uploading} />
      )}
      {importJob === null && !loading && lastWarning && (
        <div className="mb-4 rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-200">{lastWarning}</div>
      )}

      {error && (
        <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>
      )}

      {/* Insights strip */}
      {data?.insights?.length > 0 && (
        <div className="mb-4 flex gap-3 overflow-x-auto pb-1">
          {data.insights.slice(0, 4).map((i) => (
            <div key={i.kind + i.value} className="min-w-[230px] flex-1 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
              <div className="text-[11px] uppercase tracking-wider text-gray-500">{i.kind}</div>
              <div className="mt-0.5 text-sm font-semibold text-white">
                {i.value} <span className="font-normal text-fuchsia-300">×{i.lift}</span>
              </div>
              <div className="mt-1 text-xs leading-5 text-gray-400">
                {Math.round(i.listening_share * 100)}% of your listening, {Math.round(i.library_share * 100)}% of your library
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        {/* 3D view */}
        <div className="relative h-[68vh] min-h-[480px] overflow-hidden rounded-2xl border border-white/10
                        bg-[radial-gradient(ellipse_at_center,_#1a1440_0%,_#0b1121_55%,_#05070f_100%)]">
          {data && (
            <Graph3D
              data={data}
              selectedId={selectedId}
              focusIds={focusIds}
              focusCluster={clusterFocus}
              picks={picks}
              mode={tab}
              onSelect={(id) => { setSelectedId(id); if (id != null) setClusterFocus(null); }}
            />
          )}
          {loading && !importJob && !uploading && <Centered><BuildProgress estimate={buildEstimate} /></Centered>}

          {/* Legend */}
          {data && (
            <div className="pointer-events-none absolute left-3 top-3 space-y-1 rounded-xl bg-black/30 px-3 py-2 text-[11px] text-gray-300 backdrop-blur">
              <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-violet-400" /> track (bigger = played more)</div>
              <div className="flex items-center gap-2"><span className="h-0.5 w-4 bg-fuchsia-300" /> hidden connection</div>
              {tab === "picks" && <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-amber-200" /> recommended for you</div>}
            </div>
          )}
          {data && (
            <div className="pointer-events-none absolute bottom-3 left-3 text-[11px] text-gray-500">
              {data.meta.count} tracks · drag to orbit · scroll to zoom · click a star
            </div>
          )}

          {/* Selected track card */}
          {selected && (
            <div className="absolute bottom-3 right-3 w-[300px] max-w-[calc(100%-24px)] rounded-xl border border-white/10 bg-[#0b1121]/90 p-4 backdrop-blur">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate font-semibold text-white">{selected.title}</div>
                  <div className="truncate text-xs text-gray-400">{[selected.artist, selected.album].filter(Boolean).join(" · ")}</div>
                </div>
                <button onClick={() => setSelectedId(null)} className="text-gray-500 hover:text-white" aria-label="Close">✕</button>
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {selected.genre && <Chip>{selected.genre}</Chip>}
                {selected.key && <Chip>{selected.key} · {selected.camelot}</Chip>}
                {selected.bpm && <Chip>{Math.round(selected.bpm)} BPM</Chip>}
                {selected.plays != null && <Chip>{selected.plays} plays</Chip>}
              </div>
              <div className="mt-3 text-[11px] uppercase tracking-wider text-gray-500">Connected to</div>
              <div className="mt-1 max-h-40 space-y-2 overflow-y-auto pr-1">
                {selectedLinks.map((l) => (
                  <div key={l.other.id}>
                    <TrackLine t={l.other} onClick={() => setSelectedId(l.other.id)} />
                    {l.reasons?.length > 0 && (
                      <div className={`ml-4 text-[11px] ${l.kind === "hidden" ? "text-fuchsia-300" : "text-gray-500"}`}>
                        {l.kind === "hidden" && "✦ "}{l.reasons.slice(0, 2).join(" · ")}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Side panel */}
        <aside className="flex min-h-0 flex-col rounded-2xl border border-white/10 bg-white/[0.02]">
          <div className="flex gap-1 border-b border-white/10 p-2">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => { setTab(t.id); setSelectedId(null); setClusterFocus(null); }}
                className={`flex-1 rounded-lg px-2 py-1.5 text-xs font-medium transition ${
                  tab === t.id ? "bg-white/10 text-white" : "text-gray-400 hover:text-gray-200"
                }`}
              >
                {t.label}
                {t.id === "hidden" && data ? ` ${data.hidden_connections.length}` : ""}
              </button>
            ))}
          </div>

          <div className="max-h-[52vh] flex-1 space-y-3 overflow-y-auto p-4">
            {tab === "clusters" && data?.clusters.map((c) => (
              <button
                key={c.id}
                onClick={() => { setSelectedId(null); setClusterFocus(clusterFocus === c.id ? null : c.id); }}
                className={`block w-full rounded-xl border p-3 text-left transition ${
                  clusterFocus === c.id ? "border-white/25 bg-white/[0.06]" : "border-white/5 hover:border-white/15"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: colorFor(c.id), boxShadow: `0 0 10px ${colorFor(c.id)}` }} />
                    <span className="truncate text-sm font-medium text-white">{c.label}</span>
                  </div>
                  <span className="shrink-0 text-xs text-gray-500">{c.size}</span>
                </div>
                <div className="mt-2"><SignalBar value={c.signal} color={colorFor(c.id)} /></div>
                <div className="mt-1.5 text-[11px] text-gray-500">
                  {c.lift != null
                    ? `${Math.round(c.listening_share * 100)}% of your plays · ${c.lift >= 1 ? `${c.lift}× more than its size` : `${c.lift}× its size`}`
                    : "Signal = how tightly these tracks hang together"}
                </div>
              </button>
            ))}

            {tab === "hidden" && (
              <>
                <p className="text-xs leading-5 text-gray-400">
                  Pairs from different clusters that still match musically: same or neighbouring key, same or half/double tempo, similar mood.
                  Good for transitions and playlist bridges.
                </p>
                {data?.hidden_connections.length === 0 && <p className="text-sm text-gray-500">No strong cross-cluster matches yet. Add key, BPM or mood columns.</p>}
                {data?.hidden_connections.map((h, i) => (
                  <div key={i} className="rounded-xl border border-fuchsia-400/15 bg-fuchsia-400/[0.03] p-3">
                    <TrackLine t={byId[h.source]} onClick={() => setSelectedId(h.source)} />
                    <div className="my-1 ml-4 text-fuchsia-300/70">↕</div>
                    <TrackLine t={byId[h.target]} onClick={() => setSelectedId(h.target)} />
                    <div className="mt-2 text-[11px] leading-5 text-fuchsia-200/80">{h.reasons.join(" · ")}</div>
                  </div>
                ))}
              </>
            )}

            {tab === "picks" && (
              <>
                {!hasListening && (
                  <p className="text-sm leading-6 text-gray-400">
                    Add a <code className="text-gray-200">play_count</code>, <code className="text-gray-200">rating</code> or{" "}
                    <code className="text-gray-200">liked</code> column to your CSV and SuperMusic will learn your taste and suggest tracks you&apos;ve been missing.
                  </p>
                )}
                {hasListening && (
                  <p className="text-xs leading-5 text-gray-400">
                    Tracks you rarely play that sit right next to your favourites. Gold stars on the map.
                  </p>
                )}
                {data?.recommendations.map((r) => (
                  <div key={r.id} className="rounded-xl border border-amber-200/15 bg-amber-200/[0.03] p-3">
                    <TrackLine t={byId[r.id]} onClick={() => setSelectedId(r.id)} />
                    <div className="mt-2 text-[11px] leading-5 text-gray-400">
                      Because you play{" "}
                      <button className="text-amber-100 hover:underline" onClick={() => setSelectedId(r.because_you_play)}>
                        {byId[r.because_you_play]?.title}
                      </button>
                      : {r.reasons.slice(0, 2).join(" · ")}
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>

          {/* Shape the map */}
          <div className="border-t border-white/10 p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[11px] uppercase tracking-wider text-gray-500">Shape the map by</span>
              <button
                onClick={() => load(source, weights, data?.tracks?.length)}
                disabled={loading}
                className="rounded-lg bg-white/10 px-2.5 py-1 text-xs text-white hover:bg-white/15 disabled:opacity-40"
              >
                Remap
              </button>
            </div>
            <div className="grid grid-cols-1 gap-2">
              {ASPECTS.map((a) => (
                <label key={a.key} className="flex items-center gap-3 text-xs text-gray-300" title={a.hint}>
                  <span className="w-12">{a.label}</span>
                  <input
                    type="range" min="0" max="2" step="0.25"
                    value={weights[a.key]}
                    onChange={(e) => setWeights((w) => ({ ...w, [a.key]: Number(e.target.value) }))}
                    className="flex-1 accent-fuchsia-500"
                  />
                  <span className="w-8 text-right tabular-nums text-gray-500">{weights[a.key]}×</span>
                </label>
              ))}
            </div>
          </div>
        </aside>
      </div>

      {data?.meta && (
        <p className="mt-4 text-[11px] text-gray-600">
          Built from {data.meta.source === "sample" ? "the sample library" : data.meta.source} using{" "}
          {data.meta.features_used.join(", ")} · layout: {data.meta.method.toUpperCase()}
        </p>
      )}
    </PageShell>
  );
}
