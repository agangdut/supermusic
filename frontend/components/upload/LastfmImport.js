"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/router";

import { lastfmStatus } from "@/lib/api";
import PrimaryButton from "./PrimaryButton";
import ThemedCard from "./ThemedCard";

const USER_KEY = "supermusic.lastfmUser";

export function rememberedLastfmUser() {
  try { return localStorage.getItem(USER_KEY) || ""; } catch { return ""; }
}

function rememberLastfmUser(name) {
  try { localStorage.setItem(USER_KEY, name); } catch { /* not critical */ }
}

// Whether the server has a Last.fm key; null while we ask
function useLastfmEnabled() {
  const [enabled, setEnabled] = useState(null);
  useEffect(() => {
    lastfmStatus().then((r) => setEnabled(!!r?.enabled)).catch(() => setEnabled(null));
  }, []);
  return enabled;
}

function NoKeyNote() {
  return (
    <p className="rounded-lg border border-amber-300/30 bg-amber-300/[0.08] px-3 py-2 text-[11px] leading-5 text-amber-100/80">
      Last.fm import isn&apos;t set up on this server yet. Add a free <code className="text-amber-100">LASTFM_API_KEY</code> to{" "}
      <code className="text-amber-100">.env</code> (from{" "}
      <a href="https://www.last.fm/api/account/create" target="_blank" rel="noopener noreferrer" className="underline">last.fm/api</a>)
      and restart the server.
    </p>
  );
}

/** Studio card: type a Last.fm username, and the library is read and enriched in the background. */
export function LastfmCard({ onImport, busy, initialUser = "" }) {
  const enabled = useLastfmEnabled();
  const [name, setName] = useState(initialUser);
  const [lookup, setLookup] = useState(true);
  const [limit, setLimit] = useState("");
  useEffect(() => { if (!initialUser) setName(rememberedLastfmUser()); }, [initialUser]);

  const go = () => {
    const n = name.trim();
    if (!n) return;
    rememberLastfmUser(n);
    onImport(n, { lookup, limit: parseInt(limit, 10) || undefined });
  };
  const off = busy || !name.trim() || enabled === false;

  return (
    <ThemedCard
      title="Import from Last.fm"
      desc="One click, no files. We read your scrobbles, play counts and loved tracks from Last.fm, then fill in genre, tempo, key and energy."
      footer={
        <>
          <div className="text-[11px] text-gray-400">Output: one enriched .csv, ready for the map</div>
          <PrimaryButton onClick={go} disabled={off} className={off ? "opacity-50 cursor-not-allowed" : ""}>
            Import &amp; enrich
          </PrimaryButton>
        </>
      }
    >
      {enabled === false && <NoKeyNote />}
      <form onSubmit={(e) => { e.preventDefault(); go(); }} className="flex items-center gap-2">
        <span className="text-xs text-gray-400">last.fm/user/</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="your username"
          autoComplete="off"
          spellCheck={false}
          className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-2.5 py-1.5 text-sm text-white placeholder:text-gray-600"
        />
      </form>
      <label className="flex items-start gap-2 text-xs text-gray-300">
        <input type="checkbox" checked={lookup} onChange={(e) => setLookup(e.target.checked)} className="mt-0.5 accent-purple-500" />
        <span>Enrich automatically: look up each song&apos;s genre (Last.fm tags), year, tempo, key and energy.</span>
      </label>
      {lookup && (
        <label className="ml-5 flex items-center gap-2 text-xs text-gray-400">
          <span>Look up at most</span>
          <input
            type="number" min="1" max="50000" placeholder="2000" value={limit}
            onChange={(e) => setLimit(e.target.value)}
            className="w-20 rounded border border-white/10 bg-black/30 px-2 py-0.5 text-xs text-white"
          />
          <span>songs, most-played first</span>
        </label>
      )}
      <p className="text-[11px] leading-snug text-gray-500">
        Only public data is read, so no password is needed. If your profile hides recent listening, turn that off in
        Last.fm&apos;s privacy settings first. Don&apos;t use Last.fm yet? It can record what you play on Spotify, Apple Music and more.
      </p>
    </ThemedCard>
  );
}

/** Map button: asks for a username, then opens the Studio, which runs the import there. */
export function LastfmButton({ className, up = false }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const ref = useRef();
  useEffect(() => { setName(rememberedLastfmUser()); }, []);
  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  const go = (e) => {
    e.preventDefault();
    const n = name.trim();
    if (!n) return;
    rememberLastfmUser(n);
    router.push(`/upload?lastfm=${encodeURIComponent(n)}`);
  };

  return (
    <span className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} className={className} aria-expanded={open}>
        From Last.fm
      </button>
      {open && (
        <form onSubmit={go}
          className={`absolute left-0 ${up ? "bottom-9" : "top-9"} z-50 w-72 rounded-xl border border-white/10 bg-[#0f1630]/95 p-3 shadow-2xl backdrop-blur`}>
          <div className="text-xs font-semibold text-white">Import from Last.fm</div>
          <p className="mt-1 text-[11px] leading-4 text-gray-400">
            Your Last.fm username. We&apos;ll read your plays and enrich them in the Studio, where you can watch it work.
          </p>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="username"
            spellCheck={false}
            className="mt-2 w-full rounded-lg border border-white/10 bg-black/30 px-2.5 py-1.5 text-sm text-white placeholder:text-gray-600"
          />
          <button type="submit" disabled={!name.trim()}
            className="mt-2 w-full rounded-lg bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40">
            Import &amp; enrich
          </button>
        </form>
      )}
    </span>
  );
}
