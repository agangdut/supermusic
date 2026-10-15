import { useEffect, useRef, useState } from "react";
import Head from "next/head";
import { useRouter } from "next/router";

import PageShell from "@/components/layout/PageShell";
import { clearPendingSave, finishSpotifySave, pendingSave } from "@/lib/spotify";

// Spotify sends the listener back here after they sign in to save a Map Radio station
export default function SpotifyCallback() {
  const router = useRouter();
  const [status, setStatus] = useState("Signing in to Spotify…");
  const [done, setDone] = useState(null);
  const [error, setError] = useState(null);
  const [back, setBack] = useState("/map");
  const ran = useRef(false);

  useEffect(() => {
    if (!router.isReady || ran.current) return;
    ran.current = true; // the code works once; React's dev mode runs effects twice
    setBack(pendingSave()?.back || "/map");
    const { code, state, error: denied } = router.query;
    if (denied) {
      clearPendingSave();
      setError(denied === "access_denied" ? "Spotify sign-in was cancelled." : `Spotify said: ${denied}`);
      return;
    }
    finishSpotifySave({ code, state }, setStatus).then(setDone).catch((e) => setError(e.message || String(e)));
  }, [router.isReady, router.query]);

  return (
    <PageShell>
      <Head><title>Save to Spotify · SuperMusic</title></Head>
      <div className="mx-auto max-w-lg rounded-2xl border border-white/10 bg-white/[0.03] p-6">
        <h1 className="text-lg font-semibold text-white">Save to Spotify</h1>
        {!done && !error && <p className="mt-2 text-sm text-gray-400">{status}</p>}
        {error && <p className="mt-2 text-sm text-rose-300">{error}</p>}
        {done && (
          <>
            <p className="mt-2 text-sm text-gray-300">
              Added {done.added} song{done.added === 1 ? "" : "s"} to a new private playlist.
            </p>
            {done.url && (
              <a href={done.url} target="_blank" rel="noopener noreferrer"
                className="mt-3 inline-block rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:brightness-110">
                Open it in Spotify
              </a>
            )}
            {done.missing.length > 0 && (
              <div className="mt-4 text-xs text-gray-400">
                Not found on Spotify:
                <ul className="mt-1 space-y-0.5">
                  {done.missing.map((s, i) => <li key={i}>• {[s.title, s.artist].filter(Boolean).join(" · ")}</li>)}
                </ul>
              </div>
            )}
          </>
        )}
        <a href={back} className="mt-5 block text-xs text-gray-400 hover:text-white">← Back to the Music Map</a>
      </div>
    </PageShell>
  );
}
