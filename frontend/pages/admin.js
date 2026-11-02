import { useCallback, useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";

import PageShell from "@/components/layout/PageShell";
import { ago } from "@/components/social/EventLine";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/utils/fetcher";

const num = (n) => (n ?? 0).toLocaleString();
const KIND_LABEL = { map: "Shared map", profile: "Profile", pin: "Atlas note", track: "Artist track", constellation: "Atlas constellation" };
const PAGE_NAMES = { "/": "Map (home)", "/maps": "Explore", "/atlas": "Atlas", "/play": "Play", "/feed": "Feed", "/artists": "Artists",
  "/upload": "Studio", "/u/[username]": "Profiles", "/s/[id]": "Shared map pages", "/login": "Sign in", "/forgot": "Forgot password",
  "/reset": "Password reset", "/account": "Account", "/privacy": "Privacy", "/terms": "Terms" };

function Tile({ value, label, hint }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
      <div className="text-2xl font-bold tabular-nums text-white">{value}</div>
      <div className="text-xs text-gray-400">{label}</div>
      {hint && <div className="mt-0.5 text-[11px] text-gray-600">{hint}</div>}
    </div>
  );
}

/** Daily visitors as bars, with the day's numbers on hover. */
function VisitorsChart({ series }) {
  const [hover, setHover] = useState(null);
  const max = Math.max(1, ...series.map((d) => d.visitors));
  const shown = hover ?? series.length - 1;
  const d = series[shown];
  const fmt = (day) => new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-white">Visitors per day</h2>
        {d && (
          <div className="text-xs text-gray-400">
            <span className="text-gray-200">{fmt(d.day)}</span>: {num(d.visitors)} visitors · {num(d.views)} page views · {num(d.signups)} sign-ups · {num(d.jobs)} jobs
          </div>
        )}
      </div>
      <div className="relative mt-4 h-40" onMouseLeave={() => setHover(null)}>
        <div className="absolute inset-x-0 top-0 border-t border-dashed border-white/10" />
        <span className="absolute -top-4 left-0 text-[10px] text-gray-500">{num(max)}</span>
        <div className="absolute inset-0 flex items-end gap-[2px]">
          {series.map((p, i) => (
            <div key={p.day} className="flex h-full flex-1 items-end" onMouseEnter={() => setHover(i)} onFocus={() => setHover(i)} tabIndex={0}
              aria-label={`${fmt(p.day)}: ${p.visitors} visitors`}>
              <div className={`w-full rounded-t-[4px] ${i === shown ? "bg-fuchsia-300" : "bg-fuchsia-500/70"}`}
                style={{ height: `${p.visitors ? Math.max(2, (p.visitors / max) * 100) : 0}%` }} />
            </div>
          ))}
        </div>
        <div className="absolute inset-x-0 bottom-0 border-t border-white/15" />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-gray-500">
        <span>{series[0] && fmt(series[0].day)}</span>
        <span>{series.length > 1 && fmt(series[series.length - 1].day)}</span>
      </div>
    </div>
  );
}

function RankList({ title, rows, label, value, empty }) {
  const max = Math.max(1, ...rows.map(value));
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <h2 className="text-sm font-semibold text-white">{title}</h2>
      {rows.length === 0 && <p className="mt-2 text-xs text-gray-500">{empty}</p>}
      <ul className="mt-3 space-y-2">
        {rows.map((r) => (
          <li key={label(r)} className="text-xs">
            <div className="flex justify-between gap-3">
              <span className="truncate text-gray-300">{label(r)}</span>
              <span className="tabular-nums text-gray-400">{num(value(r))}</span>
            </div>
            <div className="mt-1 h-1 rounded-full bg-white/5">
              <div className="h-1 rounded-full bg-fuchsia-500/70" style={{ width: `${(value(r) / max) * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Visitors() {
  const [days, setDays] = useState(30);
  const [s, setS] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    setError(null);
    apiFetch(`/admin/stats?days=${days}`).then(setS).catch((e) => setError(e.message));
  }, [days]);
  if (error) return <p className="text-sm text-rose-300">{error}</p>;
  if (!s) return <p className="text-sm text-gray-500">Loading…</p>;
  const t = s.totals;
  return (
    <div className="space-y-4">
      <div className="flex gap-1">
        {[7, 30, 90].map((n) => (
          <button key={n} onClick={() => setDays(n)}
            className={`rounded-lg px-3 py-1.5 text-xs ${days === n ? "bg-white/10 text-white" : "text-gray-400 hover:bg-white/5"}`}>
            Last {n} days
          </button>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile value={num(t.visitors)} label="Visits" hint="each visitor counted once a day" />
        <Tile value={num(t.views)} label="Page views" />
        <Tile value={num(t.signups)} label="New accounts" hint={`${num(t.accounts)} in total`} />
        <Tile value={num(t.jobs)} label="Stems / MIDI / CSV jobs" />
      </div>
      <VisitorsChart series={s.series} />
      <div className="grid gap-4 md:grid-cols-2">
        <RankList title="Most viewed pages" rows={s.top_pages} label={(r) => PAGE_NAMES[r.path] || r.path} value={(r) => r.views}
          empty="No page views yet." />
        <RankList title="Where visitors came from" rows={s.referrers} label={(r) => r.referrer} value={(r) => r.visitors}
          empty="Nobody has arrived from another site yet (typed or bookmarked visits aren't listed)." />
      </div>
      <p className="text-[11px] leading-5 text-gray-500">
        {num(t.shared_maps)} shared maps ({num(t.listed_maps)} listed publicly). Counted without cookies or IP addresses; visitors
        who ask browsers not to be tracked aren&apos;t counted, and neither are bots.
      </p>
    </div>
  );
}

function ReportCard({ g, reasons, status, onDone }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const act = async (fn) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onDone();
    } catch (e) {
      setError(e.message || String(e));
      setBusy(false);
    }
  };
  const resolve = (action) => act(() => apiFetch(`/admin/reports/${g.id}`, { method: "POST", body: JSON.stringify({ action }) }));
  const owner = g.item?.owner;
  const deleteOwner = () => {
    if (!window.confirm(`Delete @${owner}'s account and everything it made? This can't be undone.`)) return;
    act(async () => {
      await apiFetch(`/admin/users/${encodeURIComponent(owner)}/delete`, { method: "POST" });
      if (status === "open") await apiFetch(`/admin/reports/${g.id}`, { method: "POST", body: JSON.stringify({ action: "remove" }) }).catch(() => {});
    });
  };
  return (
    <li className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-wider text-gray-500">{KIND_LABEL[g.kind]}</div>
          {g.item ? (
            <>
              <div className="truncate font-semibold text-white">{g.item.title || g.target}</div>
              {g.item.text && <p className="mt-1 max-w-xl whitespace-pre-wrap text-sm text-gray-300">&ldquo;{g.item.text}&rdquo;</p>}
              <div className="mt-1 text-xs text-gray-500">
                {owner ? <>by <Link href={`/u/${owner}`} className="text-gray-300 hover:underline">@{owner}</Link></> : g.item.by ? `by ${g.item.by}` : "anonymous"}
                {g.item.link && <> · <a href={g.item.link} target="_blank" rel="noreferrer" className="text-fuchsia-300 hover:underline">open</a></>}
              </div>
            </>
          ) : (
            <div className="text-sm text-gray-500">Already gone ({g.target})</div>
          )}
        </div>
        <div className="text-right text-xs text-gray-400">
          <div className="font-semibold text-rose-200">{g.count} report{g.count === 1 ? "" : "s"}</div>
          <div>{ago(g.first)}</div>
          {g.resolved_by && <div className="text-gray-500">{status} by @{g.resolved_by}</div>}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {Object.entries(g.reasons).map(([r, n]) => (
          <span key={r} className="rounded-md border border-white/10 px-1.5 py-0.5 text-[11px] text-gray-300">{reasons[r] || r}{n > 1 ? ` ×${n}` : ""}</span>
        ))}
      </div>
      {g.notes.length > 0 && (
        <ul className="mt-2 space-y-1">
          {g.notes.map((n, i) => <li key={i} className="text-xs text-gray-400">&ldquo;{n}&rdquo;</li>)}
        </ul>
      )}
      {error && <p className="mt-2 text-xs text-rose-300">{error}</p>}
      {status === "open" && (
        <div className="mt-3 flex flex-wrap gap-2">
          {g.item && (
            <button disabled={busy} onClick={() => resolve("remove")} className="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-500 disabled:opacity-40">
              {g.kind === "profile" ? "Clear name and bio" : "Take it down"}
            </button>
          )}
          <button disabled={busy} onClick={() => resolve("dismiss")} className="rounded-lg bg-white/10 px-3 py-1.5 text-xs text-white hover:bg-white/15 disabled:opacity-40">
            {g.item ? "Keep it (dismiss)" : "Close"}
          </button>
          {owner && (
            <button disabled={busy} onClick={deleteOwner} className="rounded-lg px-3 py-1.5 text-xs text-rose-300 hover:bg-rose-500/10 disabled:opacity-40">
              Delete @{owner}&apos;s account
            </button>
          )}
        </div>
      )}
    </li>
  );
}

function Reports({ onCount }) {
  const [status, setStatus] = useState("open");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(() => {
    setError(null);
    apiFetch(`/admin/reports?status=${status}`)
      .then((r) => { setData(r); if (status === "open") onCount(r.reports.length); })
      .catch((e) => setError(e.message));
  }, [status, onCount]);
  useEffect(() => { setData(null); load(); }, [load]);
  return (
    <div>
      <div className="flex gap-1">
        {[["open", "Waiting"], ["removed", "Taken down"], ["dismissed", "Dismissed"]].map(([id, label]) => (
          <button key={id} onClick={() => setStatus(id)}
            className={`rounded-lg px-3 py-1.5 text-xs ${status === id ? "bg-white/10 text-white" : "text-gray-400 hover:bg-white/5"}`}>
            {label}
          </button>
        ))}
      </div>
      {error && <p className="mt-4 text-sm text-rose-300">{error}</p>}
      {!data && !error && <p className="mt-4 text-sm text-gray-500">Loading…</p>}
      {data?.reports.length === 0 && (
        <p className="mt-4 text-sm text-gray-500">{status === "open" ? "Nothing waiting. Reports people send show up here." : "None yet."}</p>
      )}
      <ul className="mt-4 space-y-3">
        {data?.reports.map((g) => <ReportCard key={`${g.kind}:${g.target}`} g={g} reasons={data.reasons} status={status} onDone={load} />)}
      </ul>
    </div>
  );
}

export default function Admin() {
  const { user, ready } = useAuth();
  const [tab, setTab] = useState("visitors");
  const [open, setOpen] = useState(null);
  useEffect(() => {
    if (user?.is_admin) apiFetch("/admin/reports").then((r) => setOpen(r.reports.length)).catch(() => {});
  }, [user?.is_admin]);

  return (
    <PageShell>
      <Head><title>Admin · SuperMusic</title><meta name="robots" content="noindex" /></Head>
      <div className="mx-auto max-w-4xl">
        <h1 className="text-2xl font-bold tracking-tight text-white">Admin</h1>
        {ready && !user && <p className="mt-3 text-sm text-gray-400"><Link href="/login?next=/admin" className="text-fuchsia-300 underline">Sign in</Link> first.</p>}
        {user && !user.is_admin && (
          <p className="mt-3 text-sm text-gray-400">This page is for the site&apos;s admins. (Admins are listed in SM_ADMINS on the server.)</p>
        )}
        {user?.is_admin && (
          <>
            <div className="mt-4 flex gap-1 border-b border-white/10">
              {[["visitors", "Visitors"], ["reports", `Reports${open ? ` (${open})` : ""}`]].map(([id, label]) => (
                <button key={id} onClick={() => setTab(id)}
                  className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === id ? "border-fuchsia-400 text-white" : "border-transparent text-gray-400 hover:text-white"}`}>
                  {label}
                </button>
              ))}
            </div>
            <div className="mt-5">{tab === "visitors" ? <Visitors /> : <Reports onCount={setOpen} />}</div>
          </>
        )}
      </div>
    </PageShell>
  );
}
