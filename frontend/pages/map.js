import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Head from "next/head";
import { useRouter } from "next/router";

import PageShell from "@/components/layout/PageShell";
import { setBackgroundWork } from "@/lib/backgroundWork";
import { buildMap, getImport, getMapEstimate, getSharedMap, importLibrary, likeSongs, searchSound, skipListening } from "@/lib/api";
import { clusterGenre, clusterName, colorFor, galaxyTitle } from "@/components/map/colors";
import ImportProgress, { BuildProgress } from "@/components/map/ImportProgress";
import StatsPanel from "@/components/map/StatsPanel";
import ClusterAtlas from "@/components/map/ClusterAtlas";
import { availableLenses, buildLens, RAMP_CSS } from "@/components/map/lenses";
import RadioPanel from "@/components/map/RadioPanel";
import ShareDialog from "@/components/map/ShareDialog";
import SongStatsEditor from "@/components/map/SongStatsEditor";
import PeoplePanel from "@/components/map/PeoplePanel";

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
  { key: "sound", label: "Sound", hint: "How songs actually sound, heard by an AI model (CLAP) from each preview", needsSound: true },
];

const TABS = [
  { id: "clusters", label: "Clusters" },
  { id: "hidden", label: "Hidden links" },
  { id: "picks", label: "For you" },
  { id: "search", label: "Search", needsSound: true },
  { id: "radio", label: "Radio" },
  { id: "people", label: "People" },
];

// What each hidden link was found from (meta.hidden_by keys)
const HIDDEN_VIA = {
  listening: "played together", playlists: "same playlists", sound: "musical match", tags: "rare tag",
  features: "collaboration", artist: "same artist", album: "same album", border: "next door",
};

const EXAMPLE_SEARCHES = ["sad slow piano", "aggressive distorted guitars", "smooth jazz with saxophone", "upbeat dance with heavy bass"];

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

// Open a song on YouTube or Spotify: the CSV's own link when it has one, otherwise a search
function ListenLinks({ t }) {
  if (!t) return null;
  const q = encodeURIComponent([t.artist, t.title].filter(Boolean).join(" "));
  const links = [
    ["YouTube", t.youtube_url || `https://www.youtube.com/results?search_query=${q}`, "hover:text-rose-300"],
    ["Spotify", t.spotify_url || `https://open.spotify.com/search/${q}`, "hover:text-emerald-300"],
  ];
  return (
    <span className="flex shrink-0 gap-1">
      {links.map(([label, href, hover]) => (
        <a key={label} href={href} target="_blank" rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          title={`Open ${t.title} on ${label}`}
          className={`rounded-md border border-white/10 px-1.5 py-0.5 text-[10px] text-gray-400 transition hover:border-white/25 ${hover}`}>
          {label}
        </a>
      ))}
    </span>
  );
}

export default function MapPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [source, setSource] = useState({ sample: true });
  const [weights, setWeights] = useState({ key: 1, tempo: 1, genre: 1, mood: 1, artist: 0.5, sound: 1 });
  const mapWeightsRef = useRef(weights); // the weights the current map was drawn with
  const [query, setQuery] = useState("");
  const [found, setFound] = useState(null); // { query, results: [{ id, score }] }
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const [tab, setTab] = useState("clusters");
  const [selectedId, setSelectedId] = useState(null);
  const [clusterFocus, setClusterFocus] = useState(null);
  const fileRef = useRef();
  const requestRef = useRef(0);
  const startedRef = useRef(false);

  const [buildEstimate, setBuildEstimate] = useState(null); // seconds, when the track count is known
  const [shared, setShared] = useState(null); // the shared map being viewed: { id, title, by, ... }
  const [sharing, setSharing] = useState(false);
  const [station, setStation] = useState(null); // Map Radio's current station
  const [playingId, setPlayingId] = useState(null);
  const [radioRequest, setRadioRequest] = useState(null);

  const load = useCallback(async (src, w, tracks) => {
    const req = ++requestRef.current;
    setLoading(true);
    setError(null);
    setBuildEstimate(null);
    if (tracks) getMapEstimate(tracks).then((e) => req === requestRef.current && setBuildEstimate(e)).catch(() => {});
    try {
      const res = await buildMap({ ...src, weights: w });
      mapWeightsRef.current = w;
      if (req !== requestRef.current) return; // a newer map was requested meanwhile
      setData(res);
      setFound(null);
      setSelectedId(null);
      setClusterFocus(null);
      setTab(res.recommendations?.length ? "picks" : "clusters");
    } catch (e) {
      if (req === requestRef.current) setError(e.message || String(e));
    } finally {
      if (req === requestRef.current) setLoading(false);
    }
  }, []);

  // /map?share=<id> opens someone's shared map, as they saw it
  const openShared = useCallback(async (id) => {
    const req = ++requestRef.current;
    setLoading(true);
    setError(null);
    try {
      const s = await getSharedMap(id);
      if (req !== requestRef.current) return;
      const { map, ...meta } = s;
      setShared(meta);
      setData(map);
      // Visitors can Remap, find similar songs and search only when the share kept its song list
      setSource(meta.has_library ? { share_id: id } : null);
      const w = map.meta?.weights;
      mapWeightsRef.current = w || {};
      if (w && Object.keys(w).length) setWeights((old) => ({ ...old, ...w }));
      setFound(null);
      setSelectedId(null);
      setClusterFocus(null);
      setTab("clusters");
    } catch (e) {
      if (req === requestRef.current) setError(e.message || String(e));
    } finally {
      if (req === requestRef.current) setLoading(false);
    }
  }, []);

  // /map?csv=<server path> opens a library (e.g. from CSV enrichment); otherwise the sample
  const router = useRouter();
  useEffect(() => {
    if (!router.isReady || startedRef.current) return; // React strict mode runs effects twice in dev
    startedRef.current = true;
    const shareId = typeof router.query.share === "string" ? router.query.share : null;
    if (shareId) {
      openShared(shareId);
      return;
    }
    const csv = typeof router.query.csv === "string" ? router.query.csv : null;
    const src = csv ? { csv_path: csv } : { sample: true };
    setSource(src);
    load(src, weights);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.isReady]);

  const [pending, setPending] = useState(null); // files picked, waiting for "Build my map"
  const [enrichOnline, setEnrichOnline] = useState(true);
  const [listenPreviews, setListenPreviews] = useState(true);
  const [listenLimit, setListenLimit] = useState(""); // blank = every song (up to the import limit)
  const [lookupLimit, setLookupLimit] = useState(""); // blank = the server default (1,500)
  const [importJob, setImportJob] = useState(null);
  const [uploading, setUploading] = useState(0); // number of files being sent
  const [lastWarning, setLastWarning] = useState(null); // e.g. online lookups were skipped

  // Tell the "safe to switch" notice while an import runs
  const importing = uploading > 0 || !!importJob;
  useEffect(() => { setBackgroundWork("mapImport", importing ? 1 : 0); }, [importing]);

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
      let job = await importLibrary(files, { enrich: enrichOnline, listen: listenPreviews, listenLimit: parseInt(listenLimit, 10) || null, limit: parseInt(lookupLimit, 10) || null });
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
      mapWeightsRef.current = {}; // imports are drawn with the default weights
      setFound(null);
      setSelectedId(null);
      setClusterFocus(null);
      setTab(job.result.recommendations?.length ? "picks" : "clusters");
      setSource({ csv_path: job.result.meta.library_csv }); // so Remap works on the imported library
      setShared(null);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setUploading(0);
      setImportJob(null);
      setLoading(false);
    }
  };

  const hasSound = (data?.meta?.sound_tracks || 0) > 0;

  // "Colour by" lens: the same stars, coloured by year, plays, tempo...
  const [lensId, setLensId] = useState("cluster");
  const lenses = useMemo(() => availableLenses(data?.tracks), [data]);
  const lens = useMemo(() => buildLens(lenses.some((l) => l.id === lensId) ? lensId : "cluster", data?.tracks || []), [lensId, lenses, data]);
  const mapRef = useRef();

  const runSearch = async (text) => {
    const q = (text ?? query).trim();
    if (!q || !source) return;
    setQuery(q);
    setSearching(true);
    setSearchError(null);
    setSelectedId(null);
    setClusterFocus(null);
    try {
      setFound(await searchSound({ ...source, query: q }));
    } catch (e) {
      setSearchError(e.message || String(e));
    } finally {
      setSearching(false);
    }
  };

  // Song edits ("Fix stats") show on the labels straight away, without redrawing the 3D view; Remap moves the star
  const [patches, setPatches] = useState({});
  useEffect(() => { setPatches({}); }, [data]);
  const patchTrack = (id, patch) => setPatches((p) => ({ ...p, [id]: { ...p[id], ...patch } }));
  const byId = useMemo(
    () => Object.fromEntries((data?.tracks || []).map((t) => [t.id, patches[t.id] ? { ...t, ...patches[t.id] } : t])),
    [data, patches],
  );
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
    if (tab === "search" && found?.results.length) return new Set(found.results.map((r) => r.id));
    if (tab === "radio" && station) return new Set(station.ids);
    if (tab === "hidden") return new Set(data.hidden_connections.flatMap((h) => [h.source, h.target]));
    if (tab === "picks" && data.recommendations.length) {
      const s = new Set();
      data.recommendations.forEach((r) => { s.add(r.id); s.add(r.because_you_play); });
      return s;
    }
    return null;
  }, [data, selectedId, clusterFocus, tab, found, station]);

  const selected = selectedId != null ? byId[selectedId] : null;
  const [editing, setEditing] = useState(false); // "Fix stats" open on the selected song
  useEffect(() => { setEditing(false); }, [selectedId]);

  // "Songs you may like" for the clicked track, from the same library
  const [likes, setLikes] = useState(null); // { id, basis, results } | { id, error }
  useEffect(() => {
    if (selectedId == null || !data || !source) { setLikes(null); return; }
    let stale = false;
    setLikes({ id: selectedId, loading: true });
    likeSongs({ ...source, id: selectedId, weights: mapWeightsRef.current })
      .then((r) => { if (!stale) setLikes(r); })
      .catch((e) => { if (!stale) setLikes({ id: selectedId, error: e.message || String(e) }); });
    return () => { stale = true; };
  }, [selectedId, data, source]);
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
          {data && (
            <button
              onClick={() => setSharing(true)}
              className="rounded-xl border border-fuchsia-400/40 px-4 py-2 text-sm text-fuchsia-100 hover:bg-fuchsia-400/10"
            >
              Share
            </button>
          )}
          <input ref={fileRef} type="file" multiple accept=".csv,.json,.txt" onChange={onFile} className="hidden" />
          <button
            onClick={() => fileRef.current?.click()}
            className="rounded-xl bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-fuchsia-600/20 hover:brightness-110"
          >
            Import Spotify / Apple Music
          </button>
          <button
            onClick={() => { setShared(null); setSource({ sample: true }); load({ sample: true }, weights); }}
            className="rounded-xl border border-white/15 px-4 py-2 text-sm text-gray-200 hover:bg-white/5"
          >
            Use sample library
          </button>
          <a href="/data/sample_library.csv" download className="px-2 text-xs text-gray-400 underline-offset-2 hover:text-gray-200 hover:underline">
            CSV template
          </a>
        </div>
      </div>

      {sharing && data && (
        <ShareDialog
          data={data}
          weights={mapWeightsRef.current}
          source={source || {}}
          defaultTitle={shared ? shared.title : undefined}
          onClose={() => setSharing(false)}
        />
      )}

      {shared && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-indigo-400/20 bg-indigo-400/[0.05] px-4 py-3">
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-white">{shared.title}</div>
            <div className="text-xs text-gray-400">
              Shared by {shared.by || "someone"}
              {shared.created ? ` on ${new Date(shared.created * 1000).toLocaleDateString()}` : ""}
              {" · "}{(shared.songs || 0).toLocaleString()} songs. Try the Radio tab to listen through it.
            </div>
          </div>
          <a href="/maps" className="shrink-0 text-xs text-indigo-200 hover:text-white">More shared maps →</a>
        </div>
      )}

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
              If the CLAP service is running, the previews also give each song a &ldquo;sound&rdquo; description, which groups
              songs by how they sound and lets you search by vibe.
            </span>
          </label>
          {enrichOnline && (
            <label className="mt-2 ml-5 flex flex-wrap items-center gap-2 text-xs text-gray-300">
              <span>Look up at most</span>
              <input
                type="number" min="1" max="50000" placeholder="1500" value={lookupLimit}
                onChange={(e) => setLookupLimit(e.target.value)}
                className="w-24 rounded border border-white/10 bg-black/30 px-2 py-0.5 text-xs text-white"
              />
              <span className="text-gray-400">
                songs, most-played first. Songs without a lookup have no tempo or key, so their hidden links come only from your plays, playlists and tags.
                New songs take about half a second each; songs looked up before are instant.
              </span>
            </label>
          )}
          {enrichOnline && (
            <label className="mt-2 ml-5 flex items-start gap-2 text-xs text-gray-300">
              <input type="checkbox" checked={listenPreviews} onChange={(e) => setListenPreviews(e.target.checked)} className="mt-0.5 accent-fuchsia-500" />
              <span>
                Listen to previews for the &ldquo;sound&rdquo; description. This is the slow part of a big import; untick it to skip it.
                You can also skip it partway through. Songs heard before are remembered, so the next import is faster.
              </span>
            </label>
          )}
          {enrichOnline && listenPreviews && (
            <label className="mt-2 ml-11 flex items-center gap-2 text-xs text-gray-300">
              <span>Only listen to the</span>
              <input
                type="number"
                min="1"
                max="50000"
                placeholder="all"
                value={listenLimit}
                onChange={(e) => setListenLimit(e.target.value)}
                className="w-20 rounded border border-white/10 bg-black/30 px-2 py-0.5 text-xs text-white"
              />
              <span>most-played songs (blank = all)</span>
            </label>
          )}
          <div className="mt-3 flex gap-2">
            <button onClick={runImport} className="rounded-lg bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-3 py-1.5 text-xs font-semibold text-white">Build my map</button>
            <button onClick={() => setPending(null)} className="rounded-lg px-3 py-1.5 text-xs text-gray-400 hover:text-white">Cancel</button>
          </div>
        </div>
      )}

      {(uploading > 0 || importJob) && (
        <ImportProgress
          job={importJob}
          uploading={uploading > 0}
          fileCount={uploading}
          onSkip={async (key) => {
            if (key !== "listen" || !importJob) return;
            try {
              setImportJob(await skipListening(importJob.id));
            } catch (err) {
              setError(err.message || String(err));
            }
          }}
        />
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
        <div ref={mapRef} className="relative h-[68vh] min-h-[480px] overflow-hidden rounded-2xl border border-white/10
                        bg-[radial-gradient(ellipse_at_center,_#1a1440_0%,_#0b1121_55%,_#05070f_100%)]">
          {data && (
            <Graph3D
              data={data}
              selectedId={selectedId ?? (tab === "radio" ? playingId : null)}
              focusIds={focusIds}
              focusCluster={clusterFocus}
              picks={picks}
              mode={tab}
              colorOf={lens.colorOf}
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
              {data.meta.count.toLocaleString()} tracks · drag to orbit · scroll to zoom · click a star
            </div>
          )}

          {/* Colour by */}
          {data && lenses.length > 1 && (
            <div className="absolute right-3 top-3 w-[220px] rounded-xl bg-black/30 px-3 py-2 text-[11px] text-gray-300 backdrop-blur">
              <label className="flex items-center justify-between gap-2">
                <span className="shrink-0 text-gray-400">Colour by</span>
                <select value={lens.lens.id} onChange={(e) => setLensId(e.target.value)}
                  className="min-w-0 rounded border border-white/10 bg-[#0b1121] px-1.5 py-0.5 text-[11px] text-white">
                  {lenses.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
                </select>
              </label>
              {lens.legend?.kind === "ramp" && (
                <div className="mt-2">
                  <div className="h-1.5 rounded-full" style={{ background: RAMP_CSS }} />
                  <div className="mt-0.5 flex justify-between text-gray-400"><span>{lens.legend.lo}</span><span>{lens.legend.hi}</span></div>
                  {lens.legend.missing && <div className="mt-0.5 flex items-center gap-1.5 text-gray-500"><span className="h-2 w-2 rounded-full bg-[#3b4252]" /> no data</div>}
                </div>
              )}
              {lens.legend?.kind === "swatches" && (
                <div className="mt-2 space-y-0.5">
                  {lens.legend.items.map((it) => (
                    <div key={it.label} className="flex items-center gap-1.5 truncate">
                      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: it.color }} /> {it.label}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Selected track card */}
          {selected && (
            <div className="absolute bottom-3 right-3 max-h-[calc(100%-24px)] w-[300px] max-w-[calc(100%-24px)] overflow-y-auto rounded-xl border border-white/10 bg-[#0b1121]/90 p-4 backdrop-blur">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate font-semibold text-white">{selected.title}</div>
                  <div className="truncate text-xs text-gray-400">{[selected.artist, selected.album].filter(Boolean).join(" · ")}</div>
                </div>
                <button onClick={() => setSelectedId(null)} className="text-gray-500 hover:text-white" aria-label="Close">✕</button>
              </div>
              <button
                onClick={() => { setRadioRequest({ kind: "song", seedId: selected.id }); setTab("radio"); setSelectedId(null); }}
                className="mt-2 rounded-md border border-fuchsia-400/30 px-2 py-0.5 text-[11px] text-fuchsia-200 hover:bg-fuchsia-400/10"
              >
                ▶ Start radio from this song
              </button>
              <div className="mt-2 flex flex-wrap gap-1">
                {selected.genre && <Chip>{selected.genre}</Chip>}
                {selected.key && <Chip>{selected.camelot ? `${selected.key} · ${selected.camelot}` : selected.key}</Chip>}
                {selected.bpm && <Chip>{Math.round(selected.bpm)} BPM</Chip>}
                {selected.energy != null && <Chip>energy {Math.round(selected.energy * 100)}</Chip>}
                {selected.year && <Chip>{selected.year}</Chip>}
                {selected.plays != null && <Chip>{selected.plays} plays</Chip>}
                {selected.vibes?.map((v) => (
                  <span key={v} className="rounded-md border border-sky-300/20 bg-sky-300/[0.06] px-1.5 py-0.5 text-[11px] text-sky-200">{v}</span>
                ))}
              </div>
              <button
                onClick={() => setEditing((e) => !e)}
                className="mt-2 text-[11px] text-sky-300 hover:underline"
              >
                {editing ? "Hide song stats" : "✎ Fix stats or add a vibe"}
              </button>
              {editing && <SongStatsEditor track={selected} onChange={(patch) => patchTrack(selected.id, patch)} />}
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
            {TABS.filter((t) => !t.needsSound || hasSound).map((t) => (
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
            {selected && likes?.id === selectedId && (
              <div className="rounded-xl border border-sky-300/15 bg-sky-300/[0.03] p-3">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-[11px] uppercase tracking-wider text-sky-200/80">If you like {selected.title}</span>
                  <button onClick={() => setSelectedId(null)} className="text-[11px] text-gray-500 hover:text-white">Close</button>
                </div>
                <div className="mt-1.5 flex items-center gap-2 text-[11px] text-gray-500">
                  <span className="min-w-0 truncate">{[selected.title, selected.artist].filter(Boolean).join(" · ")}</span>
                  <ListenLinks t={selected} />
                </div>
                {likes.loading && <p className="mt-2 text-xs text-gray-500">Finding songs you may like…</p>}
                {likes.error && <p className="mt-2 text-xs text-rose-300">{likes.error}</p>}
                {likes.results && (
                  <>
                    <p className="mt-1 text-[11px] leading-5 text-gray-500">
                      {likes.basis === "sound"
                        ? "From your library, mostly by how they sound."
                        : "From your library, by key, tempo, genre and mood. Import with the CLAP service running to match by sound too."}
                    </p>
                    <div className="mt-2 space-y-2.5">
                      {likes.results.map((r) => (
                        <div key={r.id}>
                          <div className="flex items-start gap-2">
                            <div className="min-w-0 flex-1"><TrackLine t={byId[r.id]} onClick={() => setSelectedId(r.id)} /></div>
                            <ListenLinks t={byId[r.id]} />
                          </div>
                          {(r.reasons?.length > 0 || r.rarely_played) && (
                            <div className="ml-4 text-[11px] text-gray-500">
                              {[r.rarely_played && "you rarely play this", ...(r.reasons || []).slice(0, 2)].filter(Boolean).join(" · ")}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}
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
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-white" title={galaxyTitle(c)}>{clusterName(c)}</span>
                      {c.name && <span className="block truncate text-[11px] text-gray-400">{clusterGenre(c)}</span>}
                    </span>
                  </div>
                  <span className="shrink-0 text-xs text-gray-500">{c.size}</span>
                </div>
                <div className="mt-2"><SignalBar value={c.signal} color={colorFor(c.id)} /></div>
                {c.top_artists?.length > 0 && (
                  <div className="mt-1.5 truncate text-[11px] text-gray-400">{c.top_artists.slice(0, 3).map((a) => a.name).join(", ")}</div>
                )}
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
                  Pairs from different clusters that belong together anyway: songs you play back to back, songs on the same
                  playlists, musical matches (sound, key, tempo, mood), rare shared tags and collaborations. When those run
                  short, it adds an artist split across two clusters, songs from one album, and the closest neighbours
                  across a cluster border.
                </p>
                {data?.hidden_connections.length === 0 && (
                  <p className="text-sm leading-6 text-gray-500">This map has only one cluster, so there is nothing to bridge.</p>
                )}
                {data?.hidden_connections.length > 0 && data.meta.hidden_by && (
                  <p className="text-[11px] leading-5 text-gray-500">
                    {Object.entries(data.meta.hidden_by).filter(([, c]) => c).map(([k, c]) => `${c} ${HIDDEN_VIA[k]}`).join(" · ")}
                    {!data.meta.played_with_tracks && " · import your Streaming_History_Audio files too to find songs you play back to back"}
                  </p>
                )}
                {data?.hidden_connections.map((h, i) => (
                  <div key={i} className="rounded-xl border border-fuchsia-400/15 bg-fuchsia-400/[0.03] p-3">
                    <TrackLine t={byId[h.source]} onClick={() => setSelectedId(h.source)} />
                    <div className="my-1 ml-4 text-fuchsia-300/70">↕</div>
                    <TrackLine t={byId[h.target]} onClick={() => setSelectedId(h.target)} />
                    <div className="mt-2 text-[11px] leading-5 text-fuchsia-200/80">
                      {h.via && <span className="mr-1.5 rounded border border-fuchsia-300/20 px-1 py-px text-[10px] uppercase tracking-wide text-fuchsia-300/70">{HIDDEN_VIA[h.via]}</span>}
                      {h.reasons.join(" · ")}
                    </div>
                  </div>
                ))}
              </>
            )}

            {/* Kept mounted so the music keeps playing while you look at other tabs */}
            <div className={tab === "radio" ? "" : "hidden"}>
              {data && (
                <RadioPanel
                  data={data}
                  byId={byId}
                  selectedId={selectedId}
                  clusterFocus={clusterFocus}
                  request={radioRequest}
                  onStation={setStation}
                  onPlaying={setPlayingId}
                  backUrl={shared ? `/map?share=${encodeURIComponent(shared.id)}` : source?.csv_path ? `/map?csv=${encodeURIComponent(source.csv_path)}` : "/map"}
                />
              )}
            </div>

            {tab === "search" && (
              <>
                <form onSubmit={(e) => { e.preventDefault(); runSearch(); }} className="flex gap-2">
                  <input
                    id="sound-search"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Describe a sound…"
                    className="min-w-0 flex-1 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-sm text-white placeholder:text-gray-500 focus:border-fuchsia-400/50 focus:outline-none"
                  />
                  <button disabled={searching || !query.trim()} className="rounded-lg bg-white/10 px-3 text-xs text-white hover:bg-white/15 disabled:opacity-40">
                    {searching ? "…" : "Search"}
                  </button>
                </form>
                {!found && !searchError && (
                  <div className="flex flex-wrap gap-1.5">
                    {EXAMPLE_SEARCHES.map((q) => (
                      <button key={q} onClick={() => runSearch(q)} className="rounded-md border border-white/10 px-2 py-0.5 text-[11px] text-gray-400 hover:text-white">
                        {q}
                      </button>
                    ))}
                  </div>
                )}
                {searchError && <p className="text-xs text-rose-300">{searchError}</p>}
                {found && (
                  <p className="text-xs leading-5 text-gray-400">
                    Best matches for &ldquo;{found.query}&rdquo; among the {data.meta.sound_tracks} songs with a sound description. Lit up on the map.
                  </p>
                )}
                {found?.results.map((r) => (
                  <TrackLine key={r.id} t={byId[r.id]} onClick={() => setSelectedId(r.id)} />
                ))}
              </>
            )}

            {tab === "people" && (
              <PeoplePanel
                source={source}
                onSongTitle={(title, artist) => {
                  const t = data?.tracks.find((x) => x.title === title && (!artist || x.artist === artist));
                  if (t) setSelectedId(t.id);
                }}
              />
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
                disabled={loading || !source}
                title={source ? undefined : "This shared map came without its song list, so it can't be redrawn"}
                className="rounded-lg bg-white/10 px-2.5 py-1 text-xs text-white hover:bg-white/15 disabled:opacity-40"
              >
                Remap
              </button>
            </div>
            <div className="grid grid-cols-1 gap-2">
              {ASPECTS.filter((a) => !a.needsSound || hasSound).map((a) => (
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

      {data?.clusters?.length > 1 && (
        <div className="mt-6">
          <h2 className="text-lg font-semibold text-white">Your music, cluster by cluster</h2>
          <p className="mb-3 text-xs text-gray-500">
            What each part of the map is made of. Click a card to light it up on the map; click a song to fly to it.
          </p>
          <ClusterAtlas
            clusters={data.clusters}
            byId={byId}
            focusCluster={clusterFocus}
            onFocus={(id) => {
              setSelectedId(null);
              setTab("clusters");
              setClusterFocus(clusterFocus === id ? null : id);
              mapRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
            }}
            onSelect={(id) => {
              setClusterFocus(null);
              setSelectedId(id);
              mapRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
            }}
          />
        </div>
      )}

      {data?.stats && (
        <StatsPanel
          stats={data.stats}
          clusters={data.clusters}
          byId={byId}
          onSelect={(id) => {
            setClusterFocus(null);
            setSelectedId(id);
            mapRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
          }}
        />
      )}
    </PageShell>
  );
}
