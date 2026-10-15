import { useEffect, useMemo, useRef, useState } from "react";

import { colorFor } from "@/components/map/colors";
import { buildStation } from "@/components/map/radio";
import { getPreview, getYoutubeIds } from "@/lib/api";
import { SPOTIFY_CLIENT_ID, startSpotifySave } from "@/lib/spotify";

const KINDS = [
  { id: "song", label: "Around a song" },
  { id: "cluster", label: "Through a cluster" },
  { id: "journey", label: "From A to B" },
];

const songLine = (t) => [t.title, t.artist].filter(Boolean).join(" · ");

// Type to find a song; big libraries are too long for a dropdown
function SongPicker({ tracks, value, onChange, placeholder }) {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const matches = useMemo(() => {
    const q = text.trim().toLowerCase();
    if (!q) return [];
    const out = [];
    for (const t of tracks) {
      if (songLine(t).toLowerCase().includes(q)) out.push(t);
      if (out.length >= 8) break;
    }
    return out;
  }, [text, tracks]);
  return (
    <div className="relative">
      <input
        value={open ? text : value ? songLine(value) : text}
        onFocus={() => { setOpen(true); setText(""); }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onChange={(e) => setText(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-white placeholder:text-gray-500 focus:border-fuchsia-400/50 focus:outline-none"
      />
      {open && matches.length > 0 && (
        <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border border-white/10 bg-[#0b1121] shadow-xl">
          {matches.map((t) => (
            <button key={t.id} onMouseDown={() => { onChange(t.id); setOpen(false); }}
              className="block w-full truncate px-2.5 py-1.5 text-left text-xs text-gray-200 hover:bg-white/10">
              {songLine(t)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function download(name, text, type = "text/csv") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

const csvCell = (v) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));

/** Map Radio: build a station from the map, play its previews, send it to Spotify or YouTube. */
export default function RadioPanel({ data, byId, selectedId, clusterFocus, request, onPlaying, onStation, backUrl }) {
  const tracks = data?.tracks || [];
  const [kind, setKind] = useState("song");
  const [seedId, setSeedId] = useState(null);
  const [toId, setToId] = useState(null);
  const [clusterId, setClusterId] = useState(data?.clusters?.[0]?.id ?? null);
  const [length, setLength] = useState(25);
  const [station, setStation] = useState(null);
  const [pos, setPos] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [previews, setPreviews] = useState({}); // id -> { preview, deezer_url } | { error }
  const [note, setNote] = useState(null);
  const [busy, setBusy] = useState(null);
  const audioRef = useRef(null);
  const seedRef = useRef(1);

  // A new map means a new set of songs: start over
  useEffect(() => {
    setStation(null);
    setPlaying(false);
    setPreviews({});
    setClusterId(data?.clusters?.[0]?.id ?? null);
  }, [data]);

  // Follow the map: a clicked star or cluster becomes the starting point
  useEffect(() => { if (selectedId != null) setSeedId(selectedId); }, [selectedId]);
  useEffect(() => { if (clusterFocus != null) setClusterId(clusterFocus); }, [clusterFocus]);

  const start = (opts) => {
    seedRef.current = opts.seed ?? seedRef.current;
    const s = buildStation(data, { length, seed: seedRef.current, ...opts });
    if (!s) return setNote(opts.kind === "journey" ? "Pick two different songs." : "Pick where the station starts.");
    setNote(null);
    setStation(s);
    setPos(0);
    setPlaying(true);
  };

  // Another part of the page (the song card's "Start radio") can ask for a station
  useEffect(() => {
    if (!request) return;
    setKind(request.kind);
    if (request.seedId != null) setSeedId(request.seedId);
    if (request.clusterId != null) setClusterId(request.clusterId);
    start({ ...request, seed: Date.now() % 100000 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request]);

  useEffect(() => { onStation?.(station); }, [station, onStation]);
  const currentId = station ? station.ids[pos] : null;
  useEffect(() => { onPlaying?.(playing ? currentId : null); }, [currentId, playing, onPlaying]);

  // Fetch the current song's preview, and the next one's ahead of time
  const fetchPreview = async (id) => {
    if (id == null || previews[id]) return previews[id];
    const t = byId[id];
    let r;
    try {
      r = await getPreview({ artist: t.artist, title: t.title });
    } catch (e) {
      r = { error: e.message || String(e) };
    }
    setPreviews((p) => ({ ...p, [id]: r }));
    return r;
  };

  useEffect(() => {
    if (!station) return;
    fetchPreview(station.ids[pos]);
    fetchPreview(station.ids[pos + 1]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [station, pos]);

  const current = currentId != null ? previews[currentId] : null;
  const next = () => setPos((p) => (station && p + 1 < station.ids.length ? p + 1 : p));
  const prev = () => setPos((p) => Math.max(0, p - 1));

  // Play / pause / skip songs that have no preview
  useEffect(() => {
    const a = audioRef.current;
    if (!a || !station) return;
    if (!current) return; // still looking it up
    if (!current.preview) {
      if (playing) {
        if (pos + 1 < station.ids.length) next();
        else setPlaying(false);
      }
      return;
    }
    if (a.dataset.src !== current.preview) {
      a.src = current.preview;
      a.dataset.src = current.preview;
    }
    if (playing) a.play().catch(() => setPlaying(false));
    else a.pause();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, playing, station, pos]);

  const songs = station ? station.ids.map((id) => byId[id]).filter(Boolean) : [];
  const withSpotify = songs.filter((t) => t.spotify_url);
  const lastError = Object.values(previews).find((p) => p?.error)?.error;

  const copySpotify = async () => {
    try {
      await navigator.clipboard.writeText(withSpotify.map((t) => t.spotify_url).join("\n"));
      setNote(`Copied ${withSpotify.length} Spotify links. In the Spotify desktop app, open a playlist, click in the song list and press Ctrl+V (Cmd+V on a Mac).`);
    } catch {
      setNote("Your browser blocked copying. Use Download CSV instead.");
    }
  };

  const openYoutube = async () => {
    setBusy("youtube");
    setNote(null);
    // Open the tab now: browsers block pop-ups opened after a wait
    const tab = window.open("about:blank", "_blank");
    try {
      const { ids } = await getYoutubeIds(songs.slice(0, 50).map((t) => ({ title: t.title, artist: t.artist, youtube_url: t.youtube_url })));
      const found = ids.filter(Boolean);
      if (!found.length) throw new Error("No songs were found on YouTube.");
      const url = `https://www.youtube.com/watch_videos?video_ids=${found.join(",")}`;
      if (tab) tab.location.href = url;
      else window.open(url, "_blank");
      setNote(`Opened ${found.length} songs on YouTube as a playlist${found.length < songs.length ? ` (${songs.length - found.length} not found${songs.length > 50 ? "; YouTube takes 50 at most" : ""})` : ""}. Use Save on YouTube to keep it.`);
    } catch (e) {
      tab?.close();
      setNote(e.message || String(e));
    } finally {
      setBusy(null);
    }
  };

  const downloadCsv = () => {
    const rows = [["Title", "Artist", "Album", "Spotify URL"], ...songs.map((t) => [t.title, t.artist, t.album, t.spotify_url])];
    download(`${station.name}.csv`, rows.map((r) => r.map(csvCell).join(",")).join("\n") + "\n");
    setNote("Saved a CSV. Sites like TuneMyMusic or Soundiiz turn it into an Apple Music, Spotify or YouTube Music playlist.");
  };

  const saveSpotify = () => startSpotifySave({
    name: station.name,
    description: "Made with SuperMusic Map Radio",
    songs: songs.map((t) => ({ title: t.title, artist: t.artist, spotify_url: t.spotify_url })),
    back: backUrl,
  });

  const btn = "rounded-lg border border-white/10 px-2.5 py-1 text-[11px] text-gray-300 hover:border-white/25 hover:text-white disabled:opacity-40";

  return (
    <div className="space-y-3">
      <audio ref={audioRef} onEnded={() => { if (station && pos + 1 < station.ids.length) next(); else setPlaying(false); }} />
      <p className="text-xs leading-5 text-gray-400">
        A station that walks through the map, so each song sounds like the one before. Plays 30-second previews from Deezer;
        open any song on Spotify or YouTube for the full track.
      </p>

      <div className="flex gap-1">
        {KINDS.map((k) => (
          <button key={k.id} onClick={() => setKind(k.id)}
            className={`flex-1 rounded-lg px-1.5 py-1 text-[11px] ${kind === k.id ? "bg-white/10 text-white" : "text-gray-400 hover:text-gray-200"}`}>
            {k.label}
          </button>
        ))}
      </div>

      {kind === "song" && <SongPicker tracks={tracks} value={byId[seedId]} onChange={setSeedId} placeholder="Type a song, or click a star" />}
      {kind === "journey" && (
        <div className="space-y-1.5">
          <SongPicker tracks={tracks} value={byId[seedId]} onChange={setSeedId} placeholder="From… (or click a star)" />
          <SongPicker tracks={tracks} value={byId[toId]} onChange={setToId} placeholder="To…" />
        </div>
      )}
      {kind === "cluster" && (
        <select value={clusterId ?? ""} onChange={(e) => setClusterId(Number(e.target.value))}
          className="w-full rounded-lg border border-white/10 bg-[#0b1121] px-2 py-1.5 text-xs text-white">
          {(data?.clusters || []).map((c) => <option key={c.id} value={c.id}>{c.label} ({c.size})</option>)}
        </select>
      )}

      <div className="flex items-center gap-2">
        <select value={length} onChange={(e) => setLength(Number(e.target.value))}
          className="rounded-lg border border-white/10 bg-[#0b1121] px-2 py-1 text-[11px] text-white">
          {[15, 25, 50].map((n) => <option key={n} value={n}>{n} songs</option>)}
        </select>
        <button onClick={() => start({ kind, seedId, toId, clusterId, seed: 1 })}
          className="flex-1 rounded-lg bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:brightness-110">
          ▶ Start station
        </button>
      </div>

      {note && <p className="text-[11px] leading-5 text-sky-200/80">{note}</p>}

      {station && (
        <div className="rounded-xl border border-fuchsia-400/15 bg-fuchsia-400/[0.03] p-3">
          <div className="truncate text-sm font-medium text-white">{station.name}</div>
          <div className="mt-2 flex items-center gap-2">
            <button onClick={prev} className={btn} aria-label="Previous">⏮</button>
            <button onClick={() => setPlaying((p) => !p)} className={`${btn} min-w-[64px]`}>{playing ? "❚❚ Pause" : "▶ Play"}</button>
            <button onClick={next} className={btn} aria-label="Next">⏭</button>
            <button onClick={() => start({ kind: station.kind, seedId: kind === "cluster" ? null : seedId, toId, clusterId, seed: Date.now() % 100000 })}
              className={btn} title="Same start, different songs">↻ New mix</button>
          </div>
          {playing && current === undefined && <p className="mt-1 text-[11px] text-gray-500">Finding a preview…</p>}
          {lastError && <p className="mt-1 text-[11px] text-rose-300">{lastError}</p>}

          <ol className="mt-3 max-h-56 space-y-1 overflow-y-auto pr-1">
            {songs.map((t, i) => {
              const pv = previews[t.id];
              return (
                <li key={t.id}>
                  <button onClick={() => { setPos(i); setPlaying(true); }}
                    className={`flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left ${i === pos ? "bg-white/10" : "hover:bg-white/5"}`}>
                    <span className="w-4 shrink-0 text-right text-[10px] tabular-nums text-gray-500">{i === pos && playing ? "♪" : i + 1}</span>
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: colorFor(t.cluster) }} />
                    <span className="min-w-0 flex-1 truncate text-xs text-gray-200">{songLine(t)}</span>
                    {pv && !pv.preview && !pv.error && <span className="shrink-0 text-[10px] text-gray-600">no preview</span>}
                  </button>
                </li>
              );
            })}
          </ol>

          <div className="mt-3 text-[11px] uppercase tracking-wider text-gray-500">Take it with you</div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {SPOTIFY_CLIENT_ID && <button onClick={saveSpotify} className={btn}>Save to Spotify</button>}
            <button onClick={copySpotify} disabled={!withSpotify.length} className={btn}
              title={withSpotify.length ? "Paste into a Spotify playlist" : "This library has no Spotify links (Spotify exports and Exportify CSVs do)"}>
              Copy Spotify links ({withSpotify.length})
            </button>
            <button onClick={openYoutube} disabled={busy === "youtube"} className={btn}>
              {busy === "youtube" ? "Finding videos…" : "Play on YouTube"}
            </button>
            <button onClick={downloadCsv} className={btn}>Download CSV</button>
          </div>
        </div>
      )}
    </div>
  );
}
