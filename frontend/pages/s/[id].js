// A shared map's landing page: what a link in a chat opens. The server fills in the link
// preview (Open Graph tags with the share card), so chats and socials show the card.
import Head from "next/head";
import Link from "next/link";

import PageShell from "@/components/layout/PageShell";
import { Galaxies, Highlights, num } from "@/components/map/MapCards";
import UpvoteButton from "@/components/map/UpvoteButton";
import { sharedMapCard } from "@/lib/api";

const INTERNAL_API = process.env.API_INTERNAL_BASE || process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export async function getServerSideProps({ params, req }) {
  const id = String(params.id || "");
  let meta = null;
  try {
    const r = await fetch(`${INTERNAL_API}/map/shared?limit=200&sort=new`);
    // The full map can be megabytes; the list carries the same headline facts for listed maps
    const listed = r.ok ? (await r.json()).maps.find((m) => m.id === id) : null;
    if (listed) meta = listed;
    else {
      const one = await fetch(`${INTERNAL_API}/map/shared/${encodeURIComponent(id)}`);
      if (one.ok) {
        const { map, ...rest } = await one.json(); // eslint-disable-line no-unused-vars
        meta = rest;
      }
    }
  } catch {
    meta = null;
  }
  const proto = req.headers["x-forwarded-proto"] || "http";
  const origin = `${proto}://${req.headers.host}`;
  return { props: { id, meta, origin, url: `${origin}/s/${encodeURIComponent(id)}` } };
}

export default function ShareLanding({ id, meta, url, origin }) {
  if (!meta) {
    return (
      <PageShell>
        <Head><title>Map not found · SuperMusic</title></Head>
        <div className="mx-auto max-w-md py-20 text-center">
          <h1 className="text-xl font-semibold text-white">This map isn&apos;t shared any more</h1>
          <p className="mt-2 text-sm text-gray-400">Its owner may have stopped sharing it.</p>
          <Link href="/maps" className="mt-6 inline-block text-sm text-fuchsia-300 hover:underline">Explore other maps →</Link>
        </div>
      </PageShell>
    );
  }
  const s = meta.showcase || {};
  // Link previews need a full address; on the public site the API is a path on the same domain
  const card = /^https?:/.test(sharedMapCard(id)) ? sharedMapCard(id) : `${origin}${sharedMapCard(id)}`;
  const desc = `${num(s.songs ?? meta.songs)} songs in ${num(s.clusters)} galaxies${meta.by ? ` by ${meta.by}` : ""}. Explore it, or compare it with your own music.`;
  return (
    <PageShell>
      <Head>
        <title>{`${meta.title} · SuperMusic`}</title>
        <meta name="description" content={desc} />
        <meta property="og:type" content="website" />
        <meta property="og:site_name" content="SuperMusic" />
        <meta property="og:title" content={meta.title} />
        <meta property="og:description" content={desc} />
        <meta property="og:image" content={card} />
        <meta property="og:image:width" content="1200" />
        <meta property="og:image:height" content="630" />
        <meta property="og:url" content={url} />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:image" content={card} />
      </Head>

      <div className="mx-auto max-w-5xl">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={card} alt={`${meta.title}: a map of ${s.songs ?? meta.songs} songs`} className="aspect-[1200/630] w-full rounded-3xl border border-white/10 bg-black/40 shadow-2xl shadow-fuchsia-900/20" />
        <div className="mt-6 flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-white md:text-3xl">{meta.title}</h1>
            <p className="mt-1 text-sm text-gray-400">
              {meta.owner ? <>by <Link href={`/u/${meta.owner}`} className="text-gray-200 hover:underline">{meta.by || meta.owner}</Link></> : meta.by ? `by ${meta.by}` : "Shared anonymously"}
              {" · "}{num(s.songs ?? meta.songs)} songs · {num(s.artists)} artists
            </p>
            <div className="mt-4"><Galaxies s={s} max={5} /></div>
            <div className="mt-4"><Highlights s={s} limit={4} /></div>
          </div>
          <div className="flex shrink-0 flex-col gap-2 md:w-64">
            <Link href={`/?share=${encodeURIComponent(id)}`}
              className="rounded-xl bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-4 py-3 text-center text-sm font-semibold text-white shadow-lg shadow-fuchsia-600/20 hover:brightness-110">
              Explore this map
            </Link>
            <Link href={`/?compare=${encodeURIComponent(id)}`}
              className="rounded-xl border border-white/15 px-4 py-3 text-center text-sm font-semibold text-gray-100 hover:bg-white/5">
              Compare with my music
            </Link>
            <div className="flex items-center justify-center gap-3 pt-1">
              <UpvoteButton id={id} votes={meta.votes ?? 0} voted={!!meta.voted} />
              <span className="text-xs text-gray-500">Like it? Upvote it.</span>
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  );
}
