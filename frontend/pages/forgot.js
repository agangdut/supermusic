import { useEffect, useState } from "react";
import Link from "next/link";

import AuthLayout, { authButton, authInput as input } from "@/components/layout/AuthLayout";
import { Contact } from "@/components/layout/LegalPage";
import { forgotPassword, resetAvailable } from "@/lib/auth";

export default function Forgot() {
  const [login, setLogin] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { resetAvailable().then((r) => setEnabled(r.enabled)).catch(() => {}); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await forgotPassword(login.trim());
      setSent(true);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout title="Forgot your password" heading="Forgot your password?"
      intro={enabled ? "Type your username or email and we'll send a link to choose a new one." : null}
      below={<Link href="/login" className="hover:text-gray-300">Back to sign in</Link>}>
      {!enabled ? (
        <p className="mt-3 text-sm leading-6 text-gray-300">
          This site can&apos;t send email yet, so passwords can&apos;t be reset automatically. Write to <Contact /> from the
          address on your account and we&apos;ll help.
        </p>
      ) : sent ? (
        <p className="mt-4 rounded-xl bg-emerald-500/10 px-3 py-3 text-sm leading-6 text-emerald-200">
          If an account with that name or email has an email address, a link is on its way. It works for one hour.
          Check your spam folder if you don&apos;t see it.
        </p>
      ) : (
        <form onSubmit={submit} className="mt-5 space-y-3">
          <label className="block">
            <span className="text-xs text-gray-400">Username or email</span>
            <input value={login} onChange={(e) => setLogin(e.target.value)} required maxLength={254} autoComplete="username" className={input} />
          </label>
          {error && <p className="rounded-lg bg-rose-500/10 px-3 py-2 text-xs text-rose-300">{error}</p>}
          <button disabled={busy || !login.trim()} className={authButton}>{busy ? "One moment…" : "Send me a link"}</button>
          <p className="text-center text-[11px] leading-5 text-gray-500">
            No email on your account? Write to <Contact /> and we&apos;ll help.
          </p>
        </form>
      )}
    </AuthLayout>
  );
}
