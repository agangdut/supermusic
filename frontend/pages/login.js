import { useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";

import { Brand } from "@/components/layout/PageShell";
import { signIn, signUp } from "@/lib/auth";

const input = "mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white placeholder:text-gray-600 focus:border-fuchsia-400/60 focus:outline-none";

export default function Login() {
  const router = useRouter();
  const [mode, setMode] = useState(router.query.mode === "signup" ? "signup" : "signin");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const signup = mode === "signup";

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = signup ? await signUp(username.trim(), password, name.trim()) : await signIn(username.trim(), password);
      const next = typeof router.query.next === "string" && router.query.next.startsWith("/") ? router.query.next : `/u/${user.username}`;
      router.replace(next === "/login" ? "/" : next);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative grid min-h-screen place-items-center overflow-hidden bg-[#0b1121] px-4 py-12 text-gray-200">
      <Head><title>{signup ? "Create your account" : "Sign in"} · SuperMusic</title></Head>
      <div aria-hidden className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_#2a1660_0%,_#0b1121_55%)]" />
      <div aria-hidden className="pointer-events-none absolute inset-0 opacity-60"
        style={{ backgroundImage: "radial-gradient(1px 1px at 20% 30%, #fff8, transparent), radial-gradient(1px 1px at 70% 20%, #fff6, transparent), radial-gradient(1.5px 1.5px at 40% 70%, #c084fc, transparent), radial-gradient(1px 1px at 85% 60%, #38bdf8, transparent), radial-gradient(1px 1px at 10% 80%, #f472b6, transparent)" }} />

      <div className="relative w-full max-w-sm">
        <Brand className="mx-auto mb-8 w-fit" />
        <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-6 shadow-2xl backdrop-blur-md">
          <h1 className="text-xl font-bold text-white">{signup ? "Create your account" : "Welcome back"}</h1>
          <p className="mt-1 text-sm text-gray-400">
            {signup
              ? "Get a profile for your maps, follow people whose taste you like, and compare libraries."
              : "Sign in to see your feed, your maps and your weekly digest."}
          </p>

          <form onSubmit={submit} className="mt-5 space-y-3">
            <label className="block">
              <span className="text-xs text-gray-400">Username</span>
              <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required minLength={3} maxLength={50}
                pattern={signup ? "[A-Za-z0-9_.\\-]{3,50}" : undefined} title="Letters, numbers, dots, dashes and underscores" className={input} />
            </label>
            {signup && (
              <label className="block">
                <span className="text-xs text-gray-400">Display name <span className="text-gray-600">(optional)</span></span>
                <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} placeholder="How people see you" className={input} />
              </label>
            )}
            <label className="block">
              <span className="text-xs text-gray-400">Password</span>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
                minLength={signup ? 8 : 1} maxLength={72} autoComplete={signup ? "new-password" : "current-password"} className={input} />
              {signup && <span className="mt-1 block text-[11px] text-gray-500">At least 8 characters.</span>}
            </label>
            {error && <p className="rounded-lg bg-rose-500/10 px-3 py-2 text-xs text-rose-300">{error}</p>}
            <button disabled={busy}
              className="w-full rounded-xl bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-fuchsia-600/20 transition hover:brightness-110 disabled:opacity-50">
              {busy ? "One moment…" : signup ? "Create account" : "Sign in"}
            </button>
            {signup && (
              <p className="text-center text-[11px] text-gray-500">
                By creating an account you agree to the <Link href="/terms" className="underline hover:text-gray-300">terms</Link> and
                {" "}<Link href="/privacy" className="underline hover:text-gray-300">privacy policy</Link>.
              </p>
            )}
          </form>

          <p className="mt-4 text-center text-xs text-gray-400">
            {signup ? "Already have an account? " : "New here? "}
            <button onClick={() => { setMode(signup ? "signin" : "signup"); setError(null); }} className="font-medium text-fuchsia-300 hover:underline">
              {signup ? "Sign in" : "Create an account"}
            </button>
          </p>
        </div>
        <p className="mt-6 text-center text-[11px] leading-5 text-gray-500">
          Maps you shared from this browser before signing in move onto your account.
          <br /><Link href="/" className="hover:text-gray-300">Back to the map</Link>
        </p>
      </div>
    </div>
  );
}
