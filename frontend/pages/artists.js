import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";

import PageShell from "@/components/layout/PageShell";
import { colorFor } from "@/components/map/colors";
import Avatar from "@/components/ui/Avatar";
import { deleteTrack, getProfile, landTrack, setTrackPublic } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const input = "mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:border-fuchsia-400/60 focus:outline-none";

function Result({ r, onPublic }) {
  const f = r.features || {};
  return (
    <div className="space-y-5">
      <div className="rounded-3xl border border-fuchsia-400/20 bg-[radial-gradient(ellipse_at_top_left,_#2a1660_0%,_#0b1121_65%)] p-6">
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-fuchsia-300">Your track lands in</div>
        <div className="mt-2 flex items-center gap-3">
          <span className="h-4 w-4 rounded-full" style={{ background: colorFor(r.galaxy.id), boxShadow: `0 0 18px ${colorFor(r.galaxy.id)}` }} />
          <h2 className="text-2xl font-bold text-white">{r.galaxy.name}</h2>
        </div>
        <p className="mt-1 text-sm text-gray-400">{r.galaxy.label} · {r.galaxy.size} songs live there</p>
        <div className="mt-4 flex flex-wrap gap-1.5 text-[11px]">
          {f.bpm && <span className="rounded-md border border-white/10 px-1.5 py-0.5 text-gray-300">{Math.round(f.bpm)} BPM</span>}
          {f.key && <span className="rounded-md border border-white/10 px-1.5 py-0.5 text-gray-300">{f.key}{f.camelot ? ` · ${f.camelot}` : ""}</span>}
          {f.energy != null && <span className="rounded-md border border-white/10 px-1.5 py-0.5 text-gray-300">energy {Math.round(f.energy * 100)}</span>}
          <span className="rounded-md border border-white/10 px-1.5 py-0.5 text-gray-500">
            matched by {r.basis === "sound" ? "how it sounds (CLAP)" : "tempo, key, energy and genre"}
          </span>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Link href={`/atlas?track=${r.id}`} className="rounded-xl bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white">See it on the atlas</Link>
          {onPublic && (
            <label className="flex items-center gap-2 text-xs text-gray-300">
              <input type="checkbox" checked={r.public} onChange={(e) => onPublic(e.target.checked)} className="accent-fuchsia-500" />
              Show it on the atlas and my profile
            </label>
          )}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h3 className="text-sm font-semibold text-white">It sits next to</h3>
          <div className="mt-2 space-y-1.5">
            {r.neighbours.map((n) => (
              <div key={n.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="min-w-0 truncate text-gray-200">{n.title} <span className="text-gray-500">· {n.artist}</span></span>
                <span className="shrink-0 text-[11px] text-gray-500">{[n.bpm && `${Math.round(n.bpm)} BPM`, n.key].filter(Boolean).join(" · ")}</span>
              </div>
            ))}
          </div>
        </section>
        <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h3 className="text-sm font-semibold text-white">Listeners who&apos;d probably like it</h3>
          <p className="mt-0.5 text-xs text-gray-500">Public maps full of the songs it sounds like.</p>
          {r.listeners.length === 0 && <p className="mt-2 text-xs text-gray-500">None yet; the atlas is still small.</p>}
          <div className="mt-2 space-y-1.5">
            {r.listeners.map((m) => (
              <div key={m.id} className="flex items-center justify-between gap-2 text-sm">
                <Link href={`/s/${m.id}`} className="min-w-0 truncate text-gray-200 hover:text-white">{m.title}{m.by ? <span className="text-gray-500"> · {m.by}</span> : null}</Link>
                <span className="shrink-0 text-[11px] text-emerald-300">{m.songs_near} close songs</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

export default function Artists() {
  const { user } = useAuth();
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [artistName, setArtistName] = useState("");
  const [genre, setGenre] = useState("");
  const [isPublic, setIsPublic] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [mine, setMine] = useState([]);

  useEffect(() => {
    if (user) {
      setArtistName((a) => a || user.display_name);
      getProfile(user.username).then((p) => setMine(p.tracks || [])).catch(() => {});
    }
  }, [user, result]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await landTrack(file, { title, artist_name: artistName, genre, public: isPublic && !!user }));
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageShell>
      <Head><title>For artists · SuperMusic</title></Head>
      <div className="grid gap-8 lg:grid-cols-[380px_1fr]">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-fuchsia-300">For artists</div>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-white sm:text-3xl">Where does my track land?</h1>
          <p className="mt-2 text-sm leading-6 text-gray-400">
            Upload a song and see which galaxy of the <Link href="/atlas" className="text-fuchsia-300 hover:underline">community atlas</Link> it
            belongs to, the songs it sits next to, and the listeners whose maps are full of music like it. The audio is analysed and then
            deleted; only the result is kept.
          </p>
          <form onSubmit={submit} className="mt-5 space-y-3 rounded-2xl border border-white/10 bg-white/[0.03] p-5">
            <label className="block cursor-pointer rounded-xl border border-dashed border-white/15 p-4 text-center text-sm text-gray-400 hover:border-fuchsia-400/40">
              <input type="file" accept="audio/*,.mp3,.wav,.flac,.ogg,.m4a" className="hidden" onChange={(e) => {
                const f = e.target.files?.[0];
                setFile(f || null);
                if (f && !title) setTitle(f.name.replace(/\.[^.]+$/, ""));
              }} />
              {file ? <span className="text-white">{file.name}</span> : "Choose an audio file (MP3, WAV, FLAC…)"}
            </label>
            <label className="block text-xs text-gray-400">Title<input value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={120} className={input} /></label>
            <label className="block text-xs text-gray-400">Artist name<input value={artistName} onChange={(e) => setArtistName(e.target.value)} maxLength={120} className={input} /></label>
            <label className="block text-xs text-gray-400">Genre <span className="text-gray-600">(optional, helps the match)</span>
              <input value={genre} onChange={(e) => setGenre(e.target.value)} maxLength={200} placeholder="e.g. Lo-Fi, Neo-Soul" className={input} />
            </label>
            {user ? (
              <label className="flex items-center gap-2 text-xs text-gray-300">
                <input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} className="accent-fuchsia-500" />
                Put it on the atlas and my profile
              </label>
            ) : (
              <p className="text-[11px] text-gray-500"><Link href="/login?next=/artists" className="text-fuchsia-300 hover:underline">Sign in</Link> to put your track on the atlas and your profile.</p>
            )}
            {error && <p className="text-xs text-rose-300">{error}</p>}
            <button disabled={busy || !file || !title.trim()}
              className="w-full rounded-xl bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">
              {busy ? "Listening to your track…" : "Find where it lands"}
            </button>
          </form>

          {mine.length > 0 && (
            <div className="mt-6">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-white"><Avatar name={user?.display_name} username={user?.username} size={22} /> Your tracks</h2>
              <div className="mt-2 space-y-1.5">
                {mine.map((t) => (
                  <div key={t.id} className="flex items-center justify-between gap-2 rounded-xl border border-white/10 px-3 py-2">
                    <button onClick={() => setResult(t)} className="min-w-0 truncate text-left text-sm text-gray-200 hover:text-white">{t.title}</button>
                    <span className="flex shrink-0 gap-2 text-[11px]">
                      <span className="text-gray-500">{t.public ? "public" : "private"}</span>
                      <button onClick={async () => { await deleteTrack(t.id); setMine((m) => m.filter((x) => x.id !== t.id)); if (result?.id === t.id) setResult(null); }}
                        className="text-gray-500 hover:text-rose-300">remove</button>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="min-w-0">
          {result ? (
            <Result r={result} onPublic={user && result.owner !== null ? async (v) => setResult({ ...result, ...(await setTrackPublic(result.id, v)) }) : null} />
          ) : (
            <div className="grid h-full min-h-[320px] place-items-center rounded-3xl border border-dashed border-white/10 p-8 text-center">
              <div className="max-w-sm">
                <div className="mx-auto h-16 w-16 rounded-full bg-gradient-to-br from-fuchsia-500 to-indigo-600 shadow-[0_0_60px_rgba(168,85,247,0.6)]" />
                <p className="mt-6 text-sm text-gray-400">Your result shows up here: the galaxy, its neighbours, and who to play it to.</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </PageShell>
  );
}
