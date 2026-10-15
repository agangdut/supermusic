import { useState } from "react";

import { shareMap, unshareMap } from "@/lib/api";

// Shares made in this browser, with the secret token that can delete them
const MINE = "supermusic.mySharedMaps";

export function myShares() {
  try {
    return JSON.parse(localStorage.getItem(MINE) || "[]");
  } catch {
    return [];
  }
}

function rememberShare(s) {
  try {
    localStorage.setItem(MINE, JSON.stringify([s, ...myShares().filter((x) => x.id !== s.id)]));
  } catch {
    // private mode: the share still works, it just can't be deleted from here later
  }
}

export async function stopSharing(id) {
  const mine = myShares().find((s) => s.id === id);
  if (!mine) throw new Error("This map was shared from another browser.");
  try {
    await unshareMap(id, mine.delete_token);
  } catch (e) {
    if (!/already gone/.test(e.message || "")) throw e;
  }
  try {
    localStorage.setItem(MINE, JSON.stringify(myShares().filter((s) => s.id !== id)));
  } catch {
    // nothing to forget
  }
}

export const shareUrl = (id) => `${window.location.origin}/map?share=${encodeURIComponent(id)}`;

export default function ShareDialog({ data, weights, source, defaultTitle, onClose }) {
  const hasListening = !!data?.meta?.has_listening_data;
  const [title, setTitle] = useState(defaultTitle || "My music map");
  const [by, setBy] = useState("");
  const [listed, setListed] = useState(false);
  const [includeListening, setIncludeListening] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [shared, setShared] = useState(null);
  const [copied, setCopied] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const s = await shareMap({
        map: data, title: title.trim(), by: by.trim() || null, listed,
        include_listening: hasListening && includeListening, weights, source,
      });
      rememberShare({ id: s.id, title: s.title, created: s.created, delete_token: s.delete_token });
      setShared(s);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl(shared.id));
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-white/10 bg-[#0b1121] p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <h2 className="text-lg font-semibold text-white">Share this map</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white" aria-label="Close">✕</button>
        </div>

        {!shared && (
          <form onSubmit={submit} className="mt-3 space-y-3 text-sm">
            <label className="block">
              <span className="text-xs text-gray-400">Title</span>
              <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={80} required
                className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-white focus:border-fuchsia-400/50 focus:outline-none" />
            </label>
            <label className="block">
              <span className="text-xs text-gray-400">Your name (optional)</span>
              <input value={by} onChange={(e) => setBy(e.target.value)} maxLength={40} placeholder="Anonymous"
                className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-white placeholder:text-gray-600 focus:border-fuchsia-400/50 focus:outline-none" />
            </label>
            <label className="flex items-start gap-2 text-xs text-gray-300">
              <input type="checkbox" checked={listed} onChange={(e) => setListed(e.target.checked)} className="mt-0.5 accent-fuchsia-500" />
              <span>List it on <a href="/maps" target="_blank" className="text-fuchsia-300 hover:underline">Shared maps</a> so anyone can find it. Unticked, only people with the link can open it.</span>
            </label>
            {hasListening && (
              <label className="flex items-start gap-2 text-xs text-gray-300">
                <input type="checkbox" checked={includeListening} onChange={(e) => setIncludeListening(e.target.checked)} className="mt-0.5 accent-fuchsia-500" />
                <span>Include my listening data (play counts, likes, &ldquo;For you&rdquo; picks, insights and stats), so people see the map exactly as I do. Untick to share only the songs and clusters.</span>
              </label>
            )}
            <p className="text-[11px] leading-5 text-gray-500">
              People who open the link see this map with everything it was built from, can click around, Remap it and start a radio station from it. They can&apos;t change your copy.
            </p>
            {error && <p className="text-xs text-rose-300">{error}</p>}
            <button disabled={busy || !title.trim()}
              className="w-full rounded-lg bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">
              {busy ? "Sharing…" : "Create link"}
            </button>
          </form>
        )}

        {shared && (
          <div className="mt-3 space-y-3 text-sm">
            <p className="text-gray-300">Anyone with this link can open your map:</p>
            <div className="flex gap-2">
              <input readOnly value={shareUrl(shared.id)} onFocus={(e) => e.target.select()}
                className="min-w-0 flex-1 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-white" />
              <button onClick={copy} className="rounded-lg bg-white/10 px-3 text-xs text-white hover:bg-white/15">{copied ? "Copied" : "Copy"}</button>
            </div>
            <p className="text-[11px] leading-5 text-gray-500">
              You can stop sharing it from <a href="/maps" className="text-fuchsia-300 hover:underline">Shared maps</a> in this browser.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
