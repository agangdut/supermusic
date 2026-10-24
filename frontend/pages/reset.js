import { useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";

import AuthLayout, { PasswordInput, authButton } from "@/components/layout/AuthLayout";
import { resetPassword } from "@/lib/auth";

export default function Reset() {
  const router = useRouter();
  const token = typeof router.query.token === "string" ? router.query.token : "";
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    if (password !== again) {
      setError("The two passwords don't match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const user = await resetPassword(token, password);
      router.replace(`/u/${user.username}`);
    } catch (err) {
      setError(err.message || String(err));
      setBusy(false);
    }
  };

  return (
    <AuthLayout title="Choose a new password" heading="Choose a new password"
      below={<Link href="/login" className="hover:text-gray-300">Back to sign in</Link>}>
      {/* The link's token stays on this page */}
      <Head><meta name="referrer" content="no-referrer" /></Head>
      {router.isReady && !token ? (
        <p className="mt-3 text-sm text-gray-300">
          This page needs the link from your email. <Link href="/forgot" className="text-fuchsia-300 underline">Ask for a new one</Link>.
        </p>
      ) : (
        <form onSubmit={submit} className="mt-5 space-y-3">
          <label className="block">
            <span className="text-xs text-gray-400">New password</span>
            <PasswordInput value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} maxLength={72}
              autoComplete="new-password" />
            <span className="mt-1 block text-[11px] text-gray-500">At least 8 characters.</span>
          </label>
          <label className="block">
            <span className="text-xs text-gray-400">The same again</span>
            <PasswordInput value={again} onChange={(e) => setAgain(e.target.value)} required minLength={8} maxLength={72}
              autoComplete="new-password" />
          </label>
          {error && (
            <p className="rounded-lg bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
              {error} {/expired|used/.test(error) && <Link href="/forgot" className="underline">Get a new link</Link>}
            </p>
          )}
          <button disabled={busy} className={authButton}>{busy ? "One moment…" : "Save and sign in"}</button>
        </form>
      )}
    </AuthLayout>
  );
}
