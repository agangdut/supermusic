import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";

import PageShell from "@/components/layout/PageShell";
import { setBackgroundWork } from "@/lib/backgroundWork";
import { blendMaps, buildMap, getImport, getMapEstimate, getSharedMap, importLibrary, likeSongs, myMap, radioPlayed, rememberMyMap, searchSound, skipListening } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { handCsvToStudio, missingDetails } from "@/lib/handoff";
import { LastfmButton } from "@/components/upload/LastfmImport";
import ComparePanel, { CompareGate } from "@/components/map/ComparePanel";
import { clusterGenre, clusterName, colorFor, galaxyTitle } from "@/components/map/colors";
import ImportProgress, { BuildProgress } from "@/components/map/ImportProgress";
import StatsPanel from "@/components/map/StatsPanel";
import ClusterAtlas from "@/components/map/ClusterAtlas";
import { availableLenses, buildLens, RAMP_CSS } from "@/components/map/lenses";
import RadioPanel from "@/components/map/RadioPanel";
import ShareDialog from "@/components/map/ShareDialog";
import UpvoteButton from "@/components/map/UpvoteButton";
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
  { id: "compare", label: "Compare", needsBlend: true },
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

const joinWords = (w) => (w.length > 1 ? `${w.slice(0, -1).join(", ")} and ${w[w.length - 1]}` : w[0]);

export default function MapExplorer() {
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
  const [lensId, setLensId] = useState("cluster"); // "Colour by"
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

  // Compare: /?compare=<share id> draws your map and theirs as one (a blend)
  const { user } = useAuth();
  const [linkCopied, setLinkCopied] = useState(false);
  const [atTop, setAtTop] = useState(true); // hide the "facts below" cue once they scroll
  useEffect(() => {
    const onScroll = () => setAtTop(window.scrollY < 80);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  const [pendingMissing, setPendingMissing] = useState([]); // details the picked CSV lacks (genre, tempo...)
  useEffect(() => setLinkCopied(false), [shared?.id]);
  const [gate, setGate] = useState(null); // { id } while we wait for your library
  const compareRef = useRef(null); // a compare to run as soon as an import finishes
  const runCompare = useCallback(async (theirsId, mine) => {
    const req = ++requestRef.current;
    setLoading(true);
    setError(null);
    setGate(null);
    try {
      const res = await blendMaps({ mine, theirs: { share_id: theirsId } });
      if (req !== requestRef.current) return;
      setData(res);
      setShared(null);
      setSource(null); // a blend can't be remapped; open either map on its own for that
      setFound(null);
      setSelectedId(null);
      setClusterFocus(null);
      setLensId("who");
      setTab("compare");
    } catch (e) {
      if (req === requestRef.current) setError(e.message || String(e));
    } finally {
      if (req === requestRef.current) setLoading(false);
    }
  }, []);
  const startCompare = useCallback((theirsId) => {
    const mine = myMap();
    if (mine?.csv_path) return runCompare(theirsId, { csv_path: mine.csv_path });
    if (user?.has_library) return runCompare(theirsId, { account: true });
    setGate({ id: theirsId });
    if (!data) load({ sample: true }, weights); // something to look at behind the question
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runCompare, user, data]);

  // /map?csv=<server path> opens a library (e.g. from CSV enrichment); otherwise the sample
  const router = useRouter();
  // This page stays mounted when you go to other pages (see _app.js), so a link like
  // /maps -> /?share=<id> arrives as a new query, not a fresh page: follow it.
  // Plain /map keeps whatever map is open (or opens the sample the first time).
  const openedRef = useRef(null);
  const shareQuery = typeof router.query.share === "string" ? router.query.share : null;
  const csvQuery = typeof router.query.csv === "string" ? router.query.csv : null;
  const compareQuery = typeof router.query.compare === "string" ? router.query.compare : null;
  useEffect(() => {
    if (!router.isReady) return;
    if (compareQuery) {
      if (openedRef.current === `compare:${compareQuery}`) return;
      startedRef.current = true;
      openedRef.current = `compare:${compareQuery}`;
      startCompare(compareQuery);
      return;
    }
    const want = shareQuery ? `share:${shareQuery}` : csvQuery ? `csv:${csvQuery}` : null;
    if (want ? openedRef.current === want : startedRef.current) return; // also: strict mode runs effects twice in dev
    startedRef.current = true;
    openedRef.current = want;
    if (shareQuery) {
      openShared(shareQuery);
      return;
    }
    setShared(null);
    const src = csvQuery ? { csv_path: csvQuery } : { sample: true };
    setSource(src);
    load(src, weights);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.isReady, shareQuery, csvQuery, compareQuery]);

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
      setPendingMissing([]);
      setError(null);
      missingDetails(files).then(setPendingMissing).catch(() => {});
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
      rememberMyMap({ csv_path: job.result.meta.library_csv, title: job.result.meta.source });
      if (compareRef.current) {
        const theirs = compareRef.current;
        compareRef.current = null;
        runCompare(theirs, { csv_path: job.result.meta.library_csv });
      }
      setShared(null);
      openedRef.current = null; // following a share link again should reopen it
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

  const blend = data?.blend;
  const isSample = data?.meta?.source === "sample" && !shared && !blend;
  const [sheetOpen, setSheetOpen] = useState(false); // phones: the side panel is a sheet at the bottom
  const [welcomeHidden, setWelcomeHidden] = useState(true);
  useEffect(() => {
    try { setWelcomeHidden(!!window.localStorage.getItem("sm-welcome-hidden")); } catch { setWelcomeHidden(false); }
  }, []);
  const hideWelcome = () => {
    setWelcomeHidden(true);
    try { window.localStorage.setItem("sm-welcome-hidden", "1"); } catch { /* fine */ }
  };
  useEffect(() => { if (selectedId != null) setSheetOpen(false); }, [selectedId]);

  // Radio stations started on shared maps count towards the weekly radio charts
  useEffect(() => {
    if (!station) return;
    const where = shared ? `share:${shared.id}` : blend ? "blend" : isSample ? "sample" : "own";
    if (where !== "own" && where !== "blend") {
      radioPlayed({ station: `${where}:${station.kind}:${station.name}`, label: station.name, share_id: shared?.id || null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [station]);

  const importButton = (
    <button
      onClick={() => fileRef.current?.click()}
      className="rounded-lg bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow-lg shadow-fuchsia-600/20 hover:brightness-110"
    >
      {isSample ? "Import your library" : "Import"}
    </button>
  );
  const ghost = "rounded-lg border border-white/15 bg-black/20 px-3 py-1.5 text-xs text-gray-200 hover:bg-white/10";

  return (
    <PageShell bleed>
      <Head>
        <title>{shared ? `${shared.title} · SuperMusic` : "SuperMusic · your music as a galaxy"}</title>
      </Head>
      <input ref={fileRef} type="file" multiple accept=".csv,.json,.txt" onChange={onFile} className="hidden" />

      {sharing && data && (
        <ShareDialog
          data={data}
          weights={mapWeightsRef.current}
          source={source || {}}
          defaultTitle={shared ? shared.title : undefined}
          onClose={() => setSharing(false)}
        />
      )}


      {/* The map fills the screen; everything else floats on it */}
      <section
        ref={mapRef}
        className="relative h-[calc(100svh-7rem)] min-h-[460px] overflow-hidden md:h-[calc(100vh-3.5rem)]
                   bg-[radial-gradient(ellipse_at_center,_#1a1440_0%,_#0b1121_55%,_#05070f_100%)]"
      >
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

        {/* Title and actions */}
        <div className="absolute left-3 top-3 z-20 max-w-[calc(100%-24px)] md:max-w-[min(560px,calc(100%-640px))]">
          <div className="rounded-2xl border border-white/10 bg-[#0b1121]/70 px-4 py-3 backdrop-blur-md">
            <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-fuchsia-300/90">
              {blend ? "Compare" : shared ? "Shared map" : isSample ? "Sample library" : "Your music map"}
            </div>
            <h1 className="mt-0.5 truncate text-lg font-bold tracking-tight text-white md:text-2xl">
              {blend
                ? <>You <span className="text-gray-500">×</span> {blend.theirs?.title || "them"}</>
                : shared ? shared.title : isSample ? `A galaxy of ${data?.meta?.count ?? ""} songs` : "Your galaxy"}
            </h1>
            {shared && (
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-gray-400">
                <span>
                  by {shared.owner ? <Link href={`/u/${shared.owner}`} className="text-gray-200 hover:underline">{shared.by || shared.owner}</Link> : shared.by || "someone"}
                </span>
                <span>· {(shared.songs || 0).toLocaleString()} songs</span>
              </div>
            )}
            {blend && <div className="mt-0.5 text-xs text-gray-400"><b className="text-emerald-300">{blend.match}%</b> taste match · {blend.counts.both} songs in common</div>}
            {!shared && !blend && (
              <p className="mt-1 hidden text-xs leading-5 text-gray-400 md:block">
                Every star is a song. Songs that sound alike gather into galaxies, and <span className="text-fuchsia-300">pink threads</span> link songs from different worlds that belong together.
              </p>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              {importButton}
              {!shared && !blend && <LastfmButton className={ghost} />}
              {data && !blend && !shared && <button onClick={() => setSharing(true)} className={ghost}>Share</button>}
              {shared && (shared.owner && shared.owner === user?.username
                ? <button onClick={() => { navigator.clipboard?.writeText(`${window.location.origin}/s/${shared.id}`); setLinkCopied(true); }} className={ghost}>{linkCopied ? "Link copied" : "Copy link"}</button>
                : <button disabled title="Only the person who made this map can share it" className={`${ghost} cursor-not-allowed opacity-40 hover:bg-black/20`}>Share</button>)}
              {shared && <Link href={`/?compare=${encodeURIComponent(shared.id)}`} className={ghost}>Compare with mine</Link>}
              {shared && <UpvoteButton id={shared.id} votes={shared.votes ?? 0} voted={!!shared.voted} />}
              {(shared || blend || !isSample) && (
                <button
                  onClick={() => { setShared(null); openedRef.current = null; router.replace("/", undefined, { shallow: true }); const mine = myMap(); const src = mine?.csv_path && !isSample && (shared || blend) ? { csv_path: mine.csv_path } : { sample: true }; setSource(src); load(src, weights); }}
                  className="px-1.5 text-xs text-gray-400 hover:text-white"
                >
                  {(shared || blend) && myMap()?.csv_path ? "Back to my map" : "Sample"}
                </button>
              )}
            </div>
          </div>
        </div>

          {/* Colour by */}
          {data && lenses.length > 1 && (
            <div className={`absolute bottom-[80px] right-3 z-20 max-h-[40%] w-[170px] overflow-y-auto md:bottom-auto md:top-3 md:right-[400px] md:block md:max-h-none md:w-[220px] ${selected || (isSample && !welcomeHidden) ? "hidden" : ""} rounded-xl bg-black/30 px-3 py-2 text-[11px] text-gray-300 backdrop-blur`}>
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


        {/* Legend */}
        {data && !selected && !(isSample && !welcomeHidden) && (
          <div className="pointer-events-none absolute bottom-3 left-3 hidden space-y-1 rounded-xl bg-black/30 px-3 py-2 text-[11px] text-gray-300 backdrop-blur md:block">
            <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-violet-400" /> song (bigger = played more)</div>
            <div className="flex items-center gap-2"><span className="h-0.5 w-4 bg-fuchsia-300" /> hidden connection</div>
            {tab === "picks" && <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-amber-200" /> recommended for you</div>}
            <div className="pt-1 text-gray-500">{data.meta.count?.toLocaleString()} songs · drag to orbit · scroll to zoom · click a star</div>
          </div>
        )}

        {/* First visit: what am I looking at? */}
        {isSample && !welcomeHidden && !pending && !importJob && !gate && !selected && (
          <div className="absolute bottom-16 left-3 z-20 w-[min(360px,calc(100%-24px))] rounded-2xl border border-fuchsia-400/25 bg-[#0b1121]/90 p-4 shadow-2xl backdrop-blur md:bottom-24">
            <div className="flex items-start justify-between gap-2">
              <div className="text-sm font-semibold text-white">This is someone else&apos;s music</div>
              <button onClick={hideWelcome} className="text-gray-500 hover:text-white" aria-label="Close">✕</button>
            </div>
            <p className="mt-1 text-xs leading-5 text-gray-400">
              You&apos;re looking at a sample library. Import your Spotify or Apple Music history, or your Last.fm username, to see your own galaxies,
              then share the picture or compare your taste with a friend.
            </p>
            <div className="mt-3 flex gap-2">
              {importButton}
              <LastfmButton className={ghost} up />
              <Link href="/maps" className={ghost}>Explore other maps</Link>
            </div>
          </div>
        )}

        {/* Waiting for files, importing, or for your library before a compare */}
        {(pending || uploading > 0 || importJob || gate) && (
          <div className="absolute inset-0 z-40 grid place-items-center bg-black/40 p-4 backdrop-blur-[2px]">
            {gate && !pending && !uploading && !importJob && (
              <CompareGate
                id={gate.id}
                signedIn={!!user}
                onImport={() => { compareRef.current = gate.id; setGate(null); fileRef.current?.click(); }}
                onSample={() => runCompare(gate.id, { sample: true })}
                onCancel={() => { setGate(null); router.replace("/", undefined, { shallow: true }); }}
              />
            )}
      {pending && (
              <div className="max-h-full w-full max-w-lg overflow-y-auto rounded-2xl border border-fuchsia-400/25 bg-[#0b1121]/95 p-5 shadow-2xl backdrop-blur">
                <div className="text-sm font-medium text-white">Ready to import {pending.length} file{pending.length > 1 ? "s" : ""}</div>
                <ul className="mt-1 text-xs text-gray-400">
                  {pending.map((f) => <li key={f.name}>• {f.name}</li>)}
                </ul>
                {pendingMissing.length >= 2 && (
                  <div className="mt-3 rounded-xl border border-amber-300/30 bg-amber-300/[0.08] p-3">
                    <div className="text-xs font-semibold text-amber-100">This CSV is missing {joinWords(pendingMissing)}</div>
                    <p className="mt-1 text-[11px] leading-5 text-amber-100/70">
                      Without them the map can only group songs by artist, so galaxies and hidden links come out thin.
                      Do you want to enrich it in the Studio first? It fills in the gaps and keeps a clean copy you can download,
                      then you can open it straight on the map.
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button onClick={() => { handCsvToStudio(pending); setPending(null); router.push("/upload?enrich=1"); }}
                        className="rounded-lg bg-amber-300 px-3 py-1.5 text-xs font-semibold text-[#0b1121] hover:brightness-110">Enrich it in the Studio</button>
                      <span className="self-center text-[11px] text-amber-100/60">or build it here with the online lookup below</span>
                    </div>
                  </div>
                )}
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

            <div className="w-full max-w-xl">
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

            </div>
          </div>
        )}

        {(error || (importJob === null && !loading && lastWarning)) && (
          <div className="absolute left-1/2 top-3 z-30 w-[min(560px,calc(100%-24px))] -translate-x-1/2 md:top-auto md:bottom-3">
            {error && <div className="rounded-xl border border-red-500/30 bg-red-950/80 px-4 py-3 text-sm text-red-200 backdrop-blur">{error}</div>}
            {!error && <div className="rounded-xl border border-amber-400/30 bg-amber-950/80 px-4 py-3 text-sm text-amber-200 backdrop-blur">{lastWarning}</div>}
          </div>
        )}

          {/* Selected track card */}
          {selected && (
            <div className="absolute inset-x-3 bottom-16 z-30 max-h-[45%] md:inset-x-auto md:bottom-3 md:left-3 md:max-h-[calc(100%-24px)] md:w-[320px] overflow-y-auto rounded-xl border border-white/10 bg-[#0b1121]/90 p-4 backdrop-blur">
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

        {/* Side panel (desktop) / bottom sheet (phones) */}
        <aside
          className={`absolute inset-x-0 bottom-0 z-30 flex flex-col rounded-t-2xl border border-white/10 bg-[#0b1121]/90 backdrop-blur-md transition-[height] duration-300
                      md:inset-x-auto md:bottom-3 md:right-3 md:top-3 md:h-auto md:w-[380px] md:rounded-2xl ${sheetOpen ? "h-[62%]" : "h-[68px]"}`}
        >
          <button onClick={() => setSheetOpen((o) => !o)} className="flex shrink-0 justify-center py-1.5 md:hidden" aria-label={sheetOpen ? "Hide panel" : "Show panel"}>
            <span className="h-1 w-10 rounded-full bg-white/25" />
          </button>
          <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-white/10 p-1.5 [scrollbar-width:none]">
            {TABS.filter((t) => (!t.needsSound || hasSound) && (!t.needsBlend || blend)).map((t) => (
              <button
                key={t.id}
                onClick={() => { setTab(t.id); setSelectedId(null); setClusterFocus(null); setSheetOpen(true); }}
                className={`shrink-0 rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
                  tab === t.id ? "bg-white/10 text-white" : "text-gray-400 hover:text-gray-200"
                }`}
              >
                {t.label}
                {t.id === "hidden" && data ? ` ${data.hidden_connections.length}` : ""}
              </button>
            ))}
          </div>

          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {tab === "compare" && blend && (
              <ComparePanel
                blend={blend}
                clusters={data.clusters}
                focusCluster={clusterFocus}
                onFocus={(id) => { setSelectedId(null); setClusterFocus(clusterFocus === id ? null : id); }}
              />
            )}
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
                  backUrl={shared ? `/?share=${encodeURIComponent(shared.id)}` : source?.csv_path ? `/?csv=${encodeURIComponent(source.csv_path)}` : "/"}
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
          <div className="hidden border-t border-white/10 p-4 md:block">
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

        {/* There's more below the map: say so until they scroll */}
        {data && atTop && !selected && !(isSample && !welcomeHidden) && !pending && !importJob && !gate && (
          <button
            onClick={() => document.getElementById("map-facts")?.scrollIntoView({ behavior: "smooth" })}
            className="absolute bottom-[84px] left-3 z-20 flex items-center md:-translate-x-1/2 gap-2 rounded-full border border-white/15 bg-[#0b1121]/80 px-4 py-2 text-xs font-medium text-gray-100 shadow-lg shadow-black/40 backdrop-blur transition hover:border-fuchsia-400/50 hover:text-white md:bottom-5 md:left-[calc((100%-400px)/2)]"
          >
            Facts about this map
            <svg viewBox="0 0 24 24" className="h-4 w-4 animate-bounce text-fuchsia-300" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
          </button>
        )}
      </section>

      {/* Below the map: what the map is made of */}
      <div id="map-facts" className="mx-auto w-full max-w-[1400px] scroll-mt-16 px-4 pb-16 pt-8 lg:px-8">
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
              mapRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
            onSelect={(id) => {
              setClusterFocus(null);
              setSelectedId(id);
              mapRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
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
            mapRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
        />
      )}
      </div>
    </PageShell>
  );
}
