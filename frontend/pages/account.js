import { useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";

import PageShell from "@/components/layout/PageShell";
import { signOut, useAuth } from "@/lib/auth";
import { apiFetch } from "@/utils/fetcher";

const input = "mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white placeholder:text-gray-600 focus:border-red-400/60 focus:outline-none";

export default function Account() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [sure, setSure] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const remove = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/auth/me/delete", { method: "POST", body: JSON.stringify({ password }) });
      try { window.localStorage.removeItem("sm-my-map"); } catch { /* storage blocked */ }
      signOut();
      router.replace("/?deleted=1");
    } catch (err) {
      setError(err.message || String(err));
      setBusy(false);
    }
  };

  return (
    <PageShell>
      <Head><title>Your account · SuperMusic</title></Head>
      <div className="mx-auto max-w-lg">
        <h1 className="text-2xl font-bold tracking-tight text-white">Your account</h1>
        {ready && !user && (
          <p className="mt-3 text-sm text-gray-400"><Link href="/login?next=/account" className="text-fuchsia-300 underline">Sign in</Link> to manage your account.</p>
        )}
        {user && (
          <>
            <p className="mt-2 text-sm text-gray-400">Signed in as <span className="text-gray-200">@{user.username}</span>. Change your name and bio on <Link href={`/u/${user.username}`} className="text-fuchsia-300 underline">your profile</Link>.</p>

            <form onSubmit={remove} className="mt-8 rounded-2xl border border-red-500/30 bg-red-500/[0.05] p-5">
              <h2 className="text-base font-semibold text-red-100">Delete your account</h2>
              <p className="mt-1 text-sm leading-6 text-red-100/70">
                This deletes your account and everything it made: your shared maps, the library behind your map,
                your song fixes and votes, follows, pins, uploaded tracks and quiz scores. It can&apos;t be undone.
              </p>
              <label className="mt-4 block text-xs text-gray-400">Your password
                <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className={input} required />
              </label>
              <label className="mt-3 flex items-center gap-2 text-sm text-gray-300">
                <input type="checkbox" checked={sure} onChange={(e) => setSure(e.target.checked)} /> I understand this is permanent
              </label>
              {error && <p className="mt-3 text-sm text-red-300">{error}</p>}
              <button disabled={!sure || !password || busy}
                className="mt-4 rounded-xl bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-40">
                {busy ? "Deleting…" : "Delete my account"}
              </button>
            </form>
          </>
        )}
      </div>
    </PageShell>
  );
}
