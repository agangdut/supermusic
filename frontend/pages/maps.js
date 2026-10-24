import { useCallback, useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";

import PageShell from "@/components/layout/PageShell";
import { Featured, MapCard } from "@/components/map/MapCards";
import { myShares, stopSharing } from "@/components/map/ShareDialog";
import Avatar from "@/components/ui/Avatar";
import { getLeaderboards, listSharedMaps, searchPeople } from "@/lib/api";
import { onMapVote } from "@/lib/mapVotes";

const SORTS = [
  { id: "top", label: "Most upvoted" },
  { id: "week", label: "This week" },
  { id: "new", label: "Newest" },
];

function Board({ title, hint, children, empty }) {
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
      <h3 className="text-sm font-semibold text-white">{title}</h3>
      {hint && <p className="mt-0.5 text-xs text-gray-500">{hint}</p>}
      <ol className="mt-3 space-y-2">{children}</ol>
      {empty && <p className="mt-3 text-xs text-gray-500">{empty}</p>}
    </section>
  );
}

function Rank({ i }) {
  return <span className={`w-5 shrink-0 text-right text-xs tabular-nums ${i < 3 ? "font-bold text-amber-300" : "text-gray-500"}`}>{i + 1}</span>;
}

function Charts() {
  const [b, setB] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    const load = () => getLeaderboards().then(setB).catch((e) => setError(e.message || String(e)));
    load();
    // An upvote anywhere changes "Maps of the week"; fetch it again (once, if several land together)
    let t;
    const off = onMapVote(() => { clearTimeout(t); t = setTimeout(load, 600); });
    return () => { off(); clearTimeout(t); };
  }, []);
  if (error) return <p className="text-sm text-rose-300">{error}</p>;
  if (!b) return <p className="text-sm text-gray-500">Loading…</p>;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Board title="Top contributors" hint="Reputation from song fixes other listeners agreed with, being first to tag, and upvotes."
        empty={!b.contributors.length && "Nobody has earned reputation yet. Fix a song's stats on your map to start."}>
        {b.contributors.map((c, i) => (
          <li key={c.username} className="flex items-center gap-3">
            <Rank i={i} />
            <Avatar name={c.display_name} username={c.username} size={28} />
            <Link href={`/u/${c.username}`} className="min-w-0 flex-1 truncate text-sm text-gray-200 hover:text-white">{c.display_name}</Link>
            <span className="rounded-md border border-fuchsia-400/30 px-1.5 py-px text-[10px] text-fuchsia-200">{c.level}</span>
            <span className="w-14 text-right text-sm font-semibold tabular-nums text-white">{c.points}</span>
          </li>
        ))}
      </Board>
      <Board title="Radio charts" hint="The Map Radio stations most listeners started this week."
        empty={!b.radio.length && "No stations yet this week. Open a shared map and start one from the Radio tab."}>
        {b.radio.map((r, i) => (
          <li key={r.station} className="flex items-center gap-3">
            <Rank i={i} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm text-gray-200">{r.label}</div>
              {r.share_id && <Link href={`/?share=${r.share_id}`} className="truncate text-[11px] text-gray-500 hover:text-gray-300">on {r.map_title || "a shared map"}</Link>}
            </div>
            <span className="text-xs tabular-nums text-gray-400">{r.listeners} listener{r.listeners === 1 ? "" : "s"}</span>
          </li>
        ))}
      </Board>
      <Board title="Maps of the week" hint="Most upvoted in the last 7 days."
        empty={!b.maps.some((m) => m.week_votes) && "No upvotes this week yet."}>
        {b.maps.filter((m) => m.week_votes).map((m, i) => (
          <li key={m.id} className="flex items-center gap-3">
            <Rank i={i} />
            <Link href={`/s/${m.id}`} className="min-w-0 flex-1 truncate text-sm text-gray-200 hover:text-white">{m.title}</Link>
            <span className="text-xs text-gray-500">{m.by || "Anonymous"}</span>
            <span className="w-10 text-right text-sm font-semibold tabular-nums text-white">▲{m.week_votes}</span>
          </li>
        ))}
      </Board>
      <Board title="Top checkers by genre" hint="Most song-stat fixes other listeners agreed with, per genre."
        empty={!Object.keys(b.checkers || {}).length && "No agreed fixes yet. Click one of your top songs on your map and answer a quick check."}>
        {Object.entries(b.checkers || {}).slice(0, 8).map(([genre, people]) => (
          <li key={genre} className="flex items-center gap-3">
            <span className="w-24 shrink-0 truncate text-xs text-gray-400">{genre}</span>
            <span className="min-w-0 flex-1 truncate text-sm">
              {people.map((p, i) => (
                <span key={p.username}>
                  {i > 0 && <span className="text-gray-600">, </span>}
                  <Link href={`/u/${p.username}`} className={i === 0 ? "text-amber-200 hover:text-white" : "text-gray-300 hover:text-white"}>{p.username}</Link>
                  <span className="text-[11px] text-gray-500"> {p.agreed}</span>
                </span>
              ))}
            </span>
          </li>
        ))}
      </Board>
      <Board title="Music quiz" hint="Best runs this week, out of 10."
        empty={!b.quiz.length && "Nobody has played this week."}>
        {b.quiz.map((q, i) => (
          <li key={`${q.name}${i}`} className="flex items-center gap-3">
            <Rank i={i} />
            {q.username ? <Link href={`/u/${q.username}`} className="min-w-0 flex-1 truncate text-sm text-gray-200 hover:text-white">{q.name}</Link>
              : <span className="min-w-0 flex-1 truncate text-sm text-gray-200">{q.name}</span>}
            <span className="text-sm font-semibold tabular-nums text-white">{q.best}/{q.rounds}</span>
          </li>
        ))}
        <li><Link href="/play" className="text-xs font-medium text-fuchsia-300 hover:text-white">Play a round →</Link></li>
      </Board>
    </div>
  );
}

function People() {
  const [q, setQ] = useState("");
  const [users, setUsers] = useState(null);
  useEffect(() => {
    if (!q.trim()) { setUsers(null); return undefined; }
    const t = setTimeout(() => searchPeople(q).then((r) => setUsers(r.users)).catch(() => setUsers([])), 250);
    return () => clearTimeout(t);
  }, [q]);
  return (
    <div className="max-w-xl">
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name or username"
        className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white placeholder:text-gray-500 focus:border-fuchsia-400/50 focus:outline-none" />
      <div className="mt-3 space-y-1">
        {users?.length === 0 && <p className="text-sm text-gray-500">Nobody by that name yet.</p>}
        {users?.map((u) => (
          <Link key={u.username} href={`/u/${u.username}`} className="flex items-center gap-3 rounded-xl p-2 hover:bg-white/5">
            <Avatar name={u.display_name} username={u.username} size={36} />
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-white">{u.display_name} {u.is_artist && <span className="ml-1 text-[10px] text-fuchsia-300">ARTIST</span>}</div>
              <div className="truncate text-xs text-gray-500">@{u.username}{u.bio ? ` · ${u.bio}` : ""}</div>
            </div>
          </Link>
        ))}
      </div>
      {!users && <p className="mt-3 text-xs text-gray-500">Or open the People tab on your map to find listeners whose taste is closest to yours.</p>}
    </div>
  );
}

const VIEWS = [
  { id: "maps", label: "Maps" },
  { id: "charts", label: "Charts" },
  { id: "people", label: "People" },
];

export default function Explore() {
  const [view, setView] = useState("maps");
  const [sort, setSort] = useState("top");
  const [maps, setMaps] = useState(null);
  const [mine, setMine] = useState([]);
  const [error, setError] = useState(null);

  const refresh = useCallback(
    () => listSharedMaps(sort).then((r) => setMaps(r.maps)).catch((e) => setError(e.message || String(e))),
    [sort],
  );
  useEffect(() => { setMine(myShares()); }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const stop = async (id) => {
    if (!window.confirm("Stop sharing this map? The link will stop working for everyone.")) return;
    try {
      await stopSharing(id);
      setMine(myShares());
      refresh();
    } catch (e) {
      setError(e.message || String(e));
    }
  };

  const byId = Object.fromEntries((maps || []).map((m) => [m.id, m]));
  const featured = sort !== "new" && maps?.length > 2 && maps[0].votes > 0 ? maps[0] : null;
  const rest = featured ? maps.slice(1) : maps || [];

  return (
    <PageShell>
      <Head><title>Explore · SuperMusic</title></Head>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-2xl">
          <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">Explore</h1>
          <p className="mt-1 text-sm text-gray-400">
            Other people&apos;s music, drawn as galaxies. Open one to explore it, compare it with yours, or start a radio station from it.
          </p>
        </div>
        <Link href="/" className="rounded-xl bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-fuchsia-600/20 hover:brightness-110">
          Share your map
        </Link>
      </div>
      {error && <p className="mt-4 text-sm text-rose-300">{error}</p>}

      <div className="mt-6 flex flex-wrap items-center gap-4 border-b border-white/10">
        {VIEWS.map((v) => (
          <button key={v.id} onClick={() => setView(v.id)}
            className={`-mb-px border-b-2 px-1 pb-2.5 text-sm font-medium transition ${view === v.id ? "border-fuchsia-400 text-white" : "border-transparent text-gray-400 hover:text-gray-200"}`}>
            {v.label}
          </button>
        ))}
      </div>

      {view === "charts" && <div className="mt-6"><Charts /></div>}
      {view === "people" && <div className="mt-6"><People /></div>}

      {view === "maps" && (
        <>
          <div className="mt-4 flex gap-1">
            {SORTS.map((s) => (
              <button key={s.id} onClick={() => setSort(s.id)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${sort === s.id ? "bg-white/10 text-white" : "text-gray-400 hover:text-gray-200"}`}>
                {s.label}
              </button>
            ))}
          </div>

          {maps === null && !error && <p className="mt-4 text-sm text-gray-500">Loading…</p>}
          {maps?.length === 0 && (
            <div className="mt-4 rounded-2xl border border-dashed border-white/15 p-8 text-center text-sm text-gray-400">
              Nobody has listed a map yet. Open your <Link href="/" className="text-fuchsia-300 hover:underline">Music Map</Link>,
              press Share and keep &ldquo;List it&rdquo; ticked to be the first.
            </div>
          )}
          {featured && <div className="mt-4"><Featured m={featured} /></div>}
          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {rest.map((m) => <MapCard key={m.id} m={m} />)}
          </div>

          {mine.length > 0 && (
            <>
              <h2 className="mt-10 text-sm font-semibold uppercase tracking-wider text-gray-500">Shared from this browser</h2>
              <div className="mt-3 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {mine.map((m) => <MapCard key={m.id} m={{ ...m, ...byId[m.id] }} onStop={stop} />)}
              </div>
            </>
          )}
        </>
      )}
    </PageShell>
  );
}
