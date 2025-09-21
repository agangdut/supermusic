import Head from "next/head";
import { useState } from "react";
import Papa from "papaparse";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import Visualizer from "../components/Visualizer";

const ACCEPT = ".mp3,.wav,.flac,.m4a,.aac,.ogg,.opus,.csv";
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export default function Upload() {
  const [files, setFiles] = useState([]);
  const [csvFile, setCsvFile] = useState(null);
  const [audioStats, setAudioStats] = useState([]);
  const [csvStats, setCsvStats] = useState([]);
  const [tracks, setTracks] = useState([]);     // [{id, source:'audio'|'csv', name/title, url? , file? }]
  const [busy, setBusy] = useState(false);
  const [ytApiKey, setYtApiKey] = useState("");

  const addAudioTracks = (aud) => {
    const next = aud.map((f) => ({
      id: `file-${crypto.randomUUID()}`,
      source: "audio",
      name: f.name,
      file: f,
    }));
    setTracks((old) => [...old, ...next]);
  };

  const addCsvTracks = (rows) => {
    // Try to build URLs from known fields
    const urlFrom = (r) => {
      if (r["Video ID"]) return `https://www.youtube.com/watch?v=${r["Video ID"]}`;
      if (r["VideoId"])  return `https://www.youtube.com/watch?v=${r["VideoId"]}`;
      if (r["URL"])      return r["URL"];
      if (r["Url"])      return r["Url"];
      return null;
    };
    const titleFrom = (r) => r["Title"] || r["title"] || r["Video Title"] || r["Song"] || r["Track"] || r["Artist"] || "Unknown";
    const chanFrom  = (r) => r["Channel"] || r["Artist"] || r["Creator"] || r["Uploader"];
    const next = rows.map((r) => ({
      id: `csv-${crypto.randomUUID()}`,
      source: "csv",
      title: `${titleFrom(r)}`,
      channel: chanFrom(r) || "",
      url: urlFrom(r),
      raw: r,
    }));
    setTracks((old) => [...old, ...next.filter(t => t.url)]);
  };

  const computeDurations = async (audioFiles) => {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const stats = [];
    for (const f of audioFiles) {
      try {
        const buffer = await f.arrayBuffer();
        const decoded = await ctx.decodeAudioData(buffer);
        stats.push({ name: f.name, duration: Number(decoded.duration.toFixed(2)) });
      } catch {}
    }
    setAudioStats(stats);
  };

  const parseCsvForStatsAndTracks = (file) => new Promise((resolve) => {
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (res) => {
        const rows = res.data || [];
        // stats (top artists/channels)
        const artistKey = ["Artist","artist","Channel","channel","Creator","creator"].find(k => k in (rows[0] || {}));
        if (artistKey) {
          const counts = new Map();
          for (const r of rows) {
            const k = (r[artistKey] || "Unknown").toString();
            counts.set(k, (counts.get(k)||0)+1);
          }
          const top = [...counts.entries()].sort((a,b)=>b[1]-a[1]).slice(0,12).map(([label,count])=>({label,count}));
          setCsvStats(top);
        }
        addCsvTracks(rows);
        resolve();
      }
    });
  });

  const handleSelect = (e) => {
    const all = Array.from(e.target.files || []);
    const aud = all.filter(f => f.type.startsWith("audio/"));
    const csv = all.find(f => f.name.toLowerCase().endsWith(".csv")) || null;
    setFiles(aud);
    setCsvFile(csv);
    if (aud.length) addAudioTracks(aud);
  };

  const handleAnalyze = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (files.length) await computeDurations(files);
      if (csvFile) await parseCsvForStatsAndTracks(csvFile);
    } finally {
      setBusy(false);
    }
  };

  // ---- Call Python API helpers ----
  const callApiForm = async (path, formData) => {
    const res = await fetch(`${API_BASE}${path}`, { method: "POST", body: formData });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  };
  const callApiJson = async (path, payload) => {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  };

  const onConvertMidi = async () => {
    if (!files.length) return alert("Select audio files first.");
    const fd = new FormData();
    files.forEach(f => fd.append("audio", f, f.name));
    setBusy(true);
    try {
      const out = await callApiForm("/convert-midi", fd);
      alert(`MIDI job started. Check: ${API_BASE}${out.results_prefix || ""}`);
    } finally { setBusy(false); }
  };

  const onEnrichCsv = async () => {
    if (!csvFile) return alert("Select a CSV first.");
    const fd = new FormData(); fd.append("csv", csvFile, csvFile.name);
    setBusy(true);
    try {
      const out = await callApiForm("/enrich-csv", fd);
      if (out.stats?.length) setCsvStats(out.stats);
      alert("CSV enrichment done (baseline).");
    } finally { setBusy(false); }
  };

  const onSeparateStems = async () => {
    if (!files.length) return alert("Select audio files first.");
    const fd = new FormData();
    files.forEach(f => fd.append("audio", f, f.name));
    setBusy(true);
    try {
      const out = await callApiForm("/separate-stems", fd);
      alert(`Stems job started. Check: ${API_BASE}${out.results_prefix || ""}`);
    } finally { setBusy(false); }
  };

  // ---- Per-track YouTube download (CSV rows) ----
  const onDownloadTrack = async (track) => {
    if (!track?.url) return;
    if (!ytApiKey) {
      const proceed = confirm("No YouTube API key entered. Continue anyway with yt-dlp?"); 
      if (!proceed) return;
    }
    setBusy(true);
    try {
      const out = await callApiJson("/download-youtube", { url: track.url, api_key: ytApiKey });
      alert(`Download started. Check: ${API_BASE}${out.results_prefix}`);
    } catch (e) {
      console.error(e);
      alert("Failed to start download.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Head><title>Upload - SuperMusic</title></Head>
      <Navbar />
      <Sidebar
        onConvertMidi={onConvertMidi}
        onEnrichCsv={onEnrichCsv}
        onSeparateStems={onSeparateStems}
        tracks={tracks}
        onDownloadTrack={onDownloadTrack}
      />
      <main className="min-h-screen bg-gray-50 flex flex-col items-center pt-20" style={{ marginLeft: 256 }}>
        <h1 className="text-3xl font-bold mt-6">Upload Your Tracks or CSV</h1>

        <form className="mt-6 flex flex-col items-center gap-3" onSubmit={handleAnalyze}>
          <input type="file" accept={ACCEPT} multiple onChange={handleSelect} />
          <input
            type="password"
            placeholder="YouTube API Key (optional)"
            className="border rounded px-2 py-1 w-80"
            value={ytApiKey} onChange={e=>setYtApiKey(e.target.value)}
          />
          <button type="submit" disabled={busy} className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-60">
            {busy ? "Working..." : "Analyze"}
          </button>
          <p className="text-sm text-gray-500">Select multiple audio files and/or a YouTube Takeout CSV.</p>
        </form>

        <section className="w-full mt-8 px-4">
          <Visualizer audioStats={audioStats} csvStats={csvStats} />
        </section>
      </main>
    </>
  );
}
