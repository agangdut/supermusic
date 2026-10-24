import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

import AuthLayout, { authButton, authInput as input } from "@/components/layout/AuthLayout";
import { signIn, signUp } from "@/lib/auth";

export default function Login() {
  const router = useRouter();
  const [mode, setMode] = useState(router.query.mode === "signup" ? "signup" : "signin");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const signup = mode === "signup";
  // The page is prerendered, so ?mode=signup only shows up once the router is ready
  useEffect(() => { if (router.isReady && router.query.mode === "signup") setMode("signup"); }, [router.isReady, router.query.mode]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = signup ? await signUp(username.trim(), password, name.trim(), email.trim()) : await signIn(username.trim(), password);
      const next = typeof router.query.next === "string" && router.query.next.startsWith("/") ? router.query.next : `/u/${user.username}`;
      router.replace(next === "/login" ? "/" : next);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      title={signup ? "Create your account" : "Sign in"}
      heading={signup ? "Create your account" : "Welcome back"}
      intro={signup
        ? "Get a profile for your maps, follow people whose taste you like, and compare libraries."
        : "Sign in to see your feed, your maps and your weekly digest."}
      below={<>Maps you shared from this browser before signing in move onto your account.
        <br /><Link href="/" className="hover:text-gray-300">Back to the map</Link></>}
    >
      <form onSubmit={submit} className="mt-5 space-y-3">
        <label className="block">
          <span className="text-xs text-gray-400">Username</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required minLength={3} maxLength={50}
            pattern={signup ? "[A-Za-z0-9_.\\-]{3,50}" : undefined} title="Letters, numbers, dots, dashes and underscores" className={input} />
        </label>
        {signup && (
          <>
            <label className="block">
              <span className="text-xs text-gray-400">Display name <span className="text-gray-600">(optional)</span></span>
              <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} placeholder="How people see you" className={input} />
            </label>
            <label className="block">
              <span className="text-xs text-gray-400">Email <span className="text-gray-600">(optional)</span></span>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} autoComplete="email" className={input} />
              <span className="mt-1 block text-[11px] text-gray-500">Only used to send you a link if you forget your password.</span>
            </label>
          </>
        )}
        <label className="block">
          <span className="flex items-baseline justify-between text-xs text-gray-400">
            Password
            {!signup && <Link href="/forgot" className="text-[11px] text-fuchsia-300 hover:underline">Forgot it?</Link>}
          </span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
            minLength={signup ? 8 : 1} maxLength={72} autoComplete={signup ? "new-password" : "current-password"} className={input} />
          {signup && <span className="mt-1 block text-[11px] text-gray-500">At least 8 characters.</span>}
        </label>
        {error && <p className="rounded-lg bg-rose-500/10 px-3 py-2 text-xs text-rose-300">{error}</p>}
        <button disabled={busy} className={authButton}>
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
    </AuthLayout>
  );
}
