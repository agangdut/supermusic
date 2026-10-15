import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";

import PageShell from "@/components/layout/PageShell";
import EventLine from "@/components/social/EventLine";
import { getDigest, getFeed } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function search(t) {
  return `https://www.youtube.com/results?search_query=${encodeURIComponent([t.artist, t.title].filter(Boolean).join(" "))}`;
}

function Tile({ title, children, className = "" }) {
  return (
    <section className={`rounded-2xl border border-white/10 bg-white/[0.03] p-5 ${className}`}>
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">{title}</h3>
      <div className="mt-2">{children}</div>
    </section>
  );
}

const fmt = (v) => (Array.isArray(v) ? v.join(", ") : typeof v === "number" && v <= 1 ? `${Math.round(v * 100)}/100` : String(v));

function Digest({ d }) {
  return (
    <div className="rounded-3xl border border-fuchsia-400/20 bg-[radial-gradient(ellipse_at_top_left,_#2a1660_0%,_#0b1121_65%)] p-5 md:p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-fuchsia-300">{d.week}</div>
      <h2 className="mt-1 text-xl font-bold text-white">This week on your map</h2>
      <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm text-gray-300">
        <span><b className="text-white">{d.new_followers}</b> new follower{d.new_followers === 1 ? "" : "s"}</span>
        <span><b className="text-white">{d.upvotes}</b> upvote{d.upvotes === 1 ? "" : "s"} on your maps</span>
        {d.fixes && <span><b className="text-white">{d.fixes.count}</b> fixes to songs in your library</span>}
      </div>

      {!d.has_library && (
        <p className="mt-4 rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-gray-400">
          Import your library on the <Link href="/" className="text-fuchsia-300 hover:underline">map</Link> while signed in and your
          digest fills up with songs to rediscover, new listeners like you, and fixes to your songs.
        </p>
      )}

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        {d.rediscover?.length > 0 && (
          <Tile title="Rediscover from your library">
            <p className="mb-2 text-[11px] text-gray-500">Songs you own but rarely play. A fresh handful every week.</p>
            {d.rediscover.map((t) => (
              <a key={`${t.artist}|${t.title}`} href={search(t)} target="_blank" rel="noopener noreferrer" className="block truncate py-0.5 text-sm text-gray-200 hover:text-white">
                {t.title} <span className="text-gray-500">· {t.artist}</span>
              </a>
            ))}
          </Tile>
        )}
        {d.new_matches?.length > 0 && (
          <Tile title="New listeners like you">
            {d.new_matches.map((m) => (
              <Link key={m.share_id} href={`/?compare=${m.share_id}`} className="flex items-center justify-between gap-2 py-1 text-sm text-gray-200 hover:text-white">
                <span className="truncate">{m.title}{m.by ? <span className="text-gray-500"> · {m.by}</span> : null}</span>
                <span className="shrink-0 font-semibold text-emerald-300">{m.match}%</span>
              </Link>
            ))}
          </Tile>
        )}
        {d.fixes?.recent?.length > 0 && (
          <Tile title="Your songs, fixed by listeners">
            {d.fixes.recent.map((f, i) => (
              <div key={i} className="truncate py-0.5 text-sm text-gray-300">
                {f.title} <span className="text-gray-500">· {f.field} {fmt(f.value)}</span>
              </div>
            ))}
          </Tile>
        )}
        {d.from_following?.length > 0 && (
          <Tile title="Shared by people you follow">
            {d.from_following.map((m) => (
              <Link key={m.id} href={`/s/${m.id}`} className="block truncate py-0.5 text-sm text-gray-200 hover:text-white">
                {m.title} <span className="text-gray-500">· {m.actor_name}</span>
              </Link>
            ))}
          </Tile>
        )}
      </div>
      <p className="mt-4 text-[11px] text-gray-500">The digest lives here for now; email delivery needs a mail server on your SuperMusic install.</p>
    </div>
  );
}

export default function Feed() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const [feed, setFeed] = useState(null);
  const [digest, setDigest] = useState(null);
  const [error, setError] = useState(null);
  const [more, setMore] = useState(true);

  useEffect(() => {
    if (!ready) return;
    if (!user) { router.replace("/login?next=/feed"); return; }
    getFeed().then((f) => { setFeed(f); setMore(f.items.length >= 50); }).catch((e) => setError(e.message || String(e)));
    getDigest().then(setDigest).catch(() => {});
  }, [ready, user, router]);

  const loadMore = async () => {
    const last = feed.items[feed.items.length - 1];
    const f = await getFeed(last.at);
    setFeed((old) => ({ ...old, items: [...old.items, ...f.items] }));
    setMore(f.items.length >= 50);
  };

  return (
    <PageShell>
      <Head><title>Feed · SuperMusic</title></Head>
      <div className="mx-auto max-w-3xl space-y-8">
        {digest && <Digest d={digest} />}
        {error && <p className="text-sm text-rose-300">{error}</p>}
        <section>
          <h2 className="text-lg font-semibold text-white">Feed</h2>
          {feed && feed.following === 0 && (
            <p className="mt-1 text-sm text-gray-400">
              You don&apos;t follow anyone yet. Find people on <Link href="/maps" className="text-fuchsia-300 hover:underline">Explore</Link> or
              in the People tab of your map. Meanwhile, here&apos;s what everyone is up to.
            </p>
          )}
          {!feed && !error && <p className="mt-2 text-sm text-gray-500">Loading…</p>}
          <div className="mt-2 divide-y divide-white/5">
            {feed?.items.map((e) => <EventLine key={e.id} e={e} me={user?.username} />)}
          </div>
          {feed?.items.length === 0 && feed.following > 0 && <p className="mt-2 text-sm text-gray-500">Quiet so far.</p>}
          {feed && more && feed.items.length > 0 && (
            <button onClick={loadMore} className="mt-3 text-sm text-fuchsia-300 hover:underline">Older</button>
          )}
          {feed?.discover?.length > 0 && feed.following === 0 && (
            <div className="mt-2 divide-y divide-white/5">
              {feed.discover.map((e) => <EventLine key={`d${e.id}`} e={e} me={user?.username} />)}
            </div>
          )}
        </section>
      </div>
    </PageShell>
  );
}
