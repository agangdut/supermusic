import { useCallback, useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";

import PageShell from "@/components/layout/PageShell";
import { MapCard, num } from "@/components/map/MapCards";
import EventLine from "@/components/social/EventLine";
import Avatar from "@/components/ui/Avatar";
import { followList, followUser, getProfile, setMapListed, unshareMap, updateProfile } from "@/lib/api";
import { updateUser, useAuth } from "@/lib/auth";

function Stat({ value, label, onClick }) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag onClick={onClick} className={`text-left ${onClick ? "hover:text-white" : ""}`}>
      <div className="text-lg font-bold tabular-nums text-white">{value}</div>
      <div className="text-[11px] uppercase tracking-wider text-gray-500">{label}</div>
    </Tag>
  );
}

function Reputation({ rep }) {
  if (!rep) return null;
  const span = rep.next_level_at ? rep.next_level_at - rep.level_floor : 1;
  const pct = rep.next_level_at ? Math.min(100, ((rep.points - rep.level_floor) / span) * 100) : 100;
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-white">Reputation</h3>
        <span className="text-xs text-gray-500">{rep.points} points</span>
      </div>
      <div className="mt-2 text-xl font-bold text-fuchsia-200">{rep.level}</div>
      <div className="mt-2 h-1.5 rounded-full bg-white/5">
        <div className="h-1.5 rounded-full bg-gradient-to-r from-fuchsia-500 to-indigo-500" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1 text-[11px] text-gray-500">
        {rep.next_level_at ? `${rep.next_level_at - rep.points} points to the next level` : "Top level"}
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
        <div><dt className="text-gray-500">Song fixes</dt><dd className="text-base font-semibold text-white">{rep.fixes}</dd></div>
        <div><dt className="text-gray-500">Agreed by others</dt><dd className="text-base font-semibold text-white">{rep.agreed}</dd></div>
        <div><dt className="text-gray-500">First to tag</dt><dd className="text-base font-semibold text-white">{rep.first}</dd></div>
        <div><dt className="text-gray-500">Map upvotes</dt><dd className="text-base font-semibold text-white">{rep.upvotes}</dd></div>
      </dl>
      {rep.badges?.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {rep.badges.map((b) => (
            <span key={b.id} title={b.hint} className="rounded-full border border-amber-300/30 bg-amber-300/10 px-2 py-0.5 text-[11px] text-amber-200">★ {b.label}</span>
          ))}
        </div>
      )}
      <p className="mt-4 text-[11px] leading-5 text-gray-500">
        Earned by fixing song stats on your map (a fix other listeners agree with counts 10, being first to suggest it 5 more) and by upvotes on shared maps.
      </p>
    </section>
  );
}

function EditProfile({ p, onSaved, onCancel }) {
  const [name, setName] = useState(p.display_name);
  const [bio, setBio] = useState(p.bio);
  const [artist, setArtist] = useState(p.is_artist);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const u = await updateProfile({ display_name: name, bio, is_artist: artist });
      updateUser(u);
      onSaved(u);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  };
  const input = "mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-sm text-white focus:border-fuchsia-400/50 focus:outline-none";
  return (
    <form onSubmit={save} className="mt-4 max-w-md space-y-3 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <label className="block text-xs text-gray-400">Display name<input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} className={input} /></label>
      <label className="block text-xs text-gray-400">Bio<textarea value={bio} onChange={(e) => setBio(e.target.value)} maxLength={280} rows={3} className={input} placeholder="What do you listen to?" /></label>
      <label className="flex items-center gap-2 text-xs text-gray-300">
        <input type="checkbox" checked={artist} onChange={(e) => setArtist(e.target.checked)} className="accent-fuchsia-500" />
        I make music (shows an Artist badge and your tracks on the atlas)
      </label>
      {error && <p className="text-xs text-rose-300">{error}</p>}
      <div className="flex gap-2">
        <button disabled={busy} className="rounded-lg bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-3 py-1.5 text-xs font-semibold text-white">{busy ? "Saving…" : "Save"}</button>
        <button type="button" onClick={onCancel} className="px-2 text-xs text-gray-400 hover:text-white">Cancel</button>
      </div>
    </form>
  );
}

export default function Profile() {
  const router = useRouter();
  const { username } = router.query;
  const { user } = useAuth();
  const [p, setP] = useState(null);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(false);
  const [list, setList] = useState(null); // { which, users }
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (typeof username !== "string") return;
    getProfile(username).then(setP).catch((e) => setError(e.message || String(e)));
  }, [username]);
  useEffect(() => { setP(null); setList(null); load(); }, [load, user?.username]);

  const follow = async () => {
    if (!user) return router.push(`/login?next=${encodeURIComponent(router.asPath)}`);
    setBusy(true);
    try {
      const r = await followUser(p.username, !p.you_follow);
      setP((old) => ({ ...old, ...r }));
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  };
  const showList = async (which) => {
    const r = await followList(p.username, which);
    setList({ which, users: r.users });
  };
  const toggleListed = async (m) => {
    await setMapListed(m.id, !m.listed);
    load();
  };
  const remove = async (m) => {
    if (!window.confirm("Stop sharing this map? The link will stop working for everyone.")) return;
    await unshareMap(m.id, null);
    load();
  };

  if (error) return <PageShell><p className="text-sm text-rose-300">{error}</p></PageShell>;
  if (!p) return <PageShell><p className="text-sm text-gray-500">Loading…</p></PageShell>;

  const hero = p.maps[0];
  return (
    <PageShell>
      <Head><title>{p.display_name} · SuperMusic</title></Head>

      {/* Header */}
      <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-[radial-gradient(ellipse_at_top_right,_#2a1660_0%,_#0b1121_60%)] p-6 md:p-8">
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div className="flex items-center gap-4">
            <Avatar name={p.display_name} username={p.username} size={76} />
            <div className="min-w-0">
              <h1 className="truncate text-2xl font-bold text-white md:text-3xl">
                {p.display_name}
                {p.is_artist && <span className="ml-2 align-middle rounded-md border border-fuchsia-400/40 px-1.5 py-0.5 text-[10px] font-semibold tracking-wider text-fuchsia-200">ARTIST</span>}
              </h1>
              <div className="text-sm text-gray-400">@{p.username} · {p.reputation?.level}</div>
              {p.bio && <p className="mt-2 max-w-xl text-sm leading-6 text-gray-300">{p.bio}</p>}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {p.is_me ? (
              <button onClick={() => setEditing((e) => !e)} className="rounded-xl border border-white/15 px-4 py-2 text-sm text-gray-200 hover:bg-white/5">Edit profile</button>
            ) : (
              <>
                <button onClick={follow} disabled={busy}
                  className={`rounded-xl px-4 py-2 text-sm font-semibold transition ${p.you_follow ? "border border-white/15 text-gray-200 hover:bg-white/5" : "bg-gradient-to-r from-fuchsia-600 to-indigo-600 text-white hover:brightness-110"}`}>
                  {p.you_follow ? "Following" : "Follow"}
                </button>
                {hero && (
                  <Link href={`/?compare=${hero.id}`} className="rounded-xl border border-white/15 px-4 py-2 text-sm text-gray-200 hover:bg-white/5">
                    Compare with mine
                  </Link>
                )}
              </>
            )}
          </div>
        </div>
        <div className="mt-6 grid grid-cols-4 gap-3 sm:flex sm:gap-8">
          <Stat value={num(p.maps.length)} label="Maps" />
          <Stat value={num(p.followers)} label="Followers" onClick={() => showList("followers")} />
          <Stat value={num(p.following)} label="Following" onClick={() => showList("following")} />
          <Stat value={num(p.reputation?.points ?? 0)} label="Reputation" />
        </div>
        {editing && <EditProfile p={p} onSaved={() => { setEditing(false); load(); }} onCancel={() => setEditing(false)} />}
      </div>

      {list && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" onClick={() => setList(null)}>
          <div className="max-h-[70vh] w-full max-w-sm overflow-y-auto rounded-2xl border border-white/10 bg-[#0b1121] p-4" onClick={(e) => e.stopPropagation()}>
            <div className="mb-2 flex justify-between"><h2 className="text-sm font-semibold capitalize text-white">{list.which}</h2>
              <button onClick={() => setList(null)} className="text-gray-500 hover:text-white">✕</button></div>
            {list.users.length === 0 && <p className="text-sm text-gray-500">Nobody yet.</p>}
            {list.users.map((u) => (
              <Link key={u.username} href={`/u/${u.username}`} onClick={() => setList(null)} className="flex items-center gap-3 rounded-lg p-2 hover:bg-white/5">
                <Avatar name={u.display_name} username={u.username} size={32} />
                <span className="min-w-0"><span className="block truncate text-sm text-white">{u.display_name}</span><span className="block text-xs text-gray-500">@{u.username}</span></span>
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_340px]">
        <div className="min-w-0 space-y-8">
          <section>
            <h2 className="text-lg font-semibold text-white">Maps</h2>
            {p.maps.length === 0 && (
              <p className="mt-2 text-sm text-gray-500">
                {p.is_me ? <>No maps yet. <Link href="/" className="text-fuchsia-300 hover:underline">Open your map</Link> and press Share.</> : "No public maps yet."}
              </p>
            )}
            <div className="mt-3 grid gap-4 sm:grid-cols-2">
              {p.maps.map((m) => (
                <div key={m.id}>
                  <MapCard m={m} />
                  {p.is_me && (
                    <div className="mt-1.5 flex gap-3 px-1 text-[11px]">
                      <button onClick={() => toggleListed(m)} className="text-gray-400 hover:text-white">{m.listed ? "Listed publicly · hide" : "Link only · list publicly"}</button>
                      <button onClick={() => remove(m)} className="text-gray-500 hover:text-rose-300">Stop sharing</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>

          {p.tracks?.length > 0 && (
            <section>
              <h2 className="text-lg font-semibold text-white">Tracks on the atlas</h2>
              <div className="mt-3 space-y-2">
                {p.tracks.map((t) => (
                  <div key={t.id} className="flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-white">{t.title}</div>
                      <div className="truncate text-xs text-gray-500">Lands in {t.galaxy?.name}{t.galaxy?.label ? ` · ${t.galaxy.label.split(" · ")[0]}` : ""}</div>
                    </div>
                    <Link href={`/atlas?track=${t.id}`} className="shrink-0 text-xs text-fuchsia-300 hover:underline">See on atlas</Link>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section>
            <h2 className="text-lg font-semibold text-white">Activity</h2>
            {p.activity.length === 0 && <p className="mt-2 text-sm text-gray-500">Nothing yet.</p>}
            <div className="mt-1 divide-y divide-white/5">
              {p.activity.map((e) => <EventLine key={e.id} e={e} me={user?.username} />)}
            </div>
          </section>
        </div>
        <aside className="space-y-4">
          <Reputation rep={p.reputation} />
        </aside>
      </div>
    </PageShell>
  );
}
