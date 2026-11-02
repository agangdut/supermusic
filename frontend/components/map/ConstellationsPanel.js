// The "Constellations" tab of the Music Map, and the bar shown while you draw one.
// A constellation is a few songs joined by lines into a named shape (lib/constellations.js).
import { useState } from "react";
import Link from "next/link";

import { colorFor } from "@/components/map/colors";
import ReportButton from "@/components/social/ReportButton";
import { CONSTELLATION_COLORS, MAX_STARS, NAME_MAX } from "@/lib/constellations";

const songName = (t) => (t ? [t.title, t.artist].filter(Boolean).join(" · ") : "");

export function DrawingBar({ drawing, byId, onChange, onUndo, onSave, onCancel, saveLabel = "Save", saveNote = null, busy = false }) {
  const n = drawing.ids.length;
  const last = n ? byId[drawing.ids[n - 1]] : null;
  const btn = "rounded-lg px-3 py-1.5 text-xs";
  return (
    <div className="absolute inset-x-3 bottom-3 z-30 rounded-2xl border border-sky-300/30 bg-[#0b1121]/95 p-3 shadow-2xl shadow-black/50 backdrop-blur
                    md:inset-x-auto md:left-[calc((100%-400px)/2)] md:w-[440px] md:-translate-x-1/2">
      {!drawing.naming ? (
        <>
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-semibold text-white">
              {drawing.editId ? "Edit constellation" : drawing.title || "Draw a constellation"}
              <span className="ml-2 text-xs font-normal text-sky-200">{n} star{n === 1 ? "" : "s"}</span>
            </div>
            <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: drawing.color, boxShadow: `0 0 10px ${drawing.color}` }} />
          </div>
          <p className="mt-1 truncate text-xs text-gray-400">
            {n === 0 ? "Tap stars on the map, one after another. Each one is joined to the last."
              : n >= MAX_STARS ? `That's the most a constellation can have (${MAX_STARS}).`
                : <>Last: <span className="text-gray-200">{songName(last)}</span></>}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button disabled={n < 2} onClick={() => onChange({ naming: true })}
              className={`${btn} bg-sky-300 font-semibold text-[#0b1121] hover:brightness-110 disabled:opacity-40`}>
              Done
            </button>
            <button disabled={!n} onClick={onUndo} className={`${btn} border border-white/15 text-gray-200 hover:bg-white/10 disabled:opacity-40`}>Undo</button>
            <button onClick={onCancel} className={`${btn} text-gray-400 hover:text-white`}>Cancel</button>
          </div>
        </>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); onSave(); }}>
          <div className="text-sm font-semibold text-white">Name your constellation</div>
          <input
            autoFocus
            value={drawing.name}
            maxLength={NAME_MAX}
            onChange={(e) => onChange({ name: e.target.value })}
            placeholder="Night drive, Gym, Rainy Sunday…"
            className="mt-2 w-full rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-sm text-white placeholder:text-gray-500 focus:border-sky-300/50 focus:outline-none"
          />
          <div className="mt-2 flex items-center gap-1.5">
            {CONSTELLATION_COLORS.map((c) => (
              <button type="button" key={c} onClick={() => onChange({ color: c })} aria-label={`Colour ${c}`}
                className={`h-6 w-6 rounded-full border-2 ${drawing.color === c ? "border-white" : "border-transparent"}`}
                style={{ background: c, boxShadow: `0 0 8px ${c}` }} />
            ))}
          </div>
          {saveNote && <p className="mt-2 text-[11px] leading-4 text-gray-400">{saveNote}</p>}
          <div className="mt-3 flex gap-2">
            <button disabled={busy} className={`${btn} bg-sky-300 font-semibold text-[#0b1121] hover:brightness-110 disabled:opacity-50`}>{busy ? "…" : saveLabel}</button>
            <button type="button" onClick={() => onChange({ naming: false })} className={`${btn} border border-white/15 text-gray-200 hover:bg-white/10`}>Back to stars</button>
          </div>
        </form>
      )}
    </div>
  );
}

export default function ConstellationsPanel({ shapes, total, editable, where, signedIn, error, active, show, byId,
  onShow, onPick, onSong, onNew, onEdit, onDelete }) {
  const [confirm, setConfirm] = useState(null);
  const hidden = total - shapes.length; // saved, but their songs aren't on this map
  return (
    <>
      <p className="text-xs leading-5 text-gray-400">
        {where === "shared"
          ? "Shapes the owner of this map drew by joining songs. Tap one to fly to it."
          : "Join songs with lines into your own shapes: a mood, a memory, a playlist. Tap one to fly to it."}
      </p>
      {editable && (
        <div className="flex items-center gap-2">
          <button onClick={onNew} disabled={total >= 30}
            className="rounded-lg bg-gradient-to-r from-sky-500 to-indigo-500 px-3 py-1.5 text-xs font-semibold text-white hover:brightness-110 disabled:opacity-40">
            ✦ New constellation
          </button>
          {shapes.length > 0 && (
            <label className="flex items-center gap-1.5 text-[11px] text-gray-400">
              <input type="checkbox" checked={show} onChange={(e) => onShow(e.target.checked)} className="accent-sky-400" /> Show on map
            </label>
          )}
        </div>
      )}
      {editable && (
        <p className="text-[11px] leading-4 text-gray-500">
          {where === "sample" ? "On the sample map they're kept in this browser."
            : signedIn ? "Saved on your account, so they show on every device you sign in on. Shares of this map include them."
              : "Kept in this browser. Sign in to keep them on your account. Shares of this map include them."}
        </p>
      )}
      {error && <p className="text-[11px] text-amber-300">{error}</p>}
      {!shapes.length && (
        <p className="text-sm leading-6 text-gray-500">
          {where === "shared" ? "This map has no constellations." : "No constellations yet."}
        </p>
      )}
      {shapes.map((c) => (
        <div key={c.id}
          className={`rounded-xl border p-2.5 transition md:p-3 ${active === c.id ? "border-white/25 bg-white/[0.06]" : "border-white/5 hover:border-white/15"}`}>
          <button onClick={() => onPick(c)} className="flex w-full items-center justify-between gap-2 text-left">
            <span className="flex min-w-0 items-center gap-2">
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: c.color, boxShadow: `0 0 10px ${c.color}` }} />
              <span className="truncate text-sm font-medium text-white">{c.name}</span>
            </span>
            <span className="shrink-0 text-xs text-gray-500">{c.ids.length} stars</span>
          </button>
          {active === c.id && (
            <>
              <ol className="mt-2 space-y-1">
                {c.ids.map((id, i) => byId[id] && (
                  <li key={`${id}-${i}`}>
                    <button onClick={() => onSong(id)} className="flex w-full items-center gap-2 text-left text-xs text-gray-300 hover:text-white">
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: colorFor(byId[id].cluster) }} />
                      <span className="truncate">{songName(byId[id])}</span>
                    </button>
                  </li>
                ))}
              </ol>
              {c.missing > 0 && <p className="mt-1 text-[11px] text-gray-500">{c.missing} of its songs aren&apos;t on this map.</p>}
              {editable && (
                <div className="mt-2 flex gap-3 text-[11px]">
                  <button onClick={() => onEdit(c)} className="text-sky-300 hover:underline">Edit</button>
                  {confirm === c.id
                    ? <button onClick={() => { setConfirm(null); onDelete(c); }} className="text-rose-300 hover:underline">Yes, delete it</button>
                    : <button onClick={() => setConfirm(c.id)} className="text-gray-400 hover:text-rose-300">Delete</button>}
                </div>
              )}
            </>
          )}
        </div>
      ))}
      {hidden > 0 && (
        <p className="text-[11px] text-gray-500">
          {hidden} saved constellation{hidden > 1 ? "s are" : " is"} hidden because {hidden > 1 ? "their" : "its"} songs aren&apos;t on this map.
        </p>
      )}
    </>
  );
}

/** Atlas tab: official constellations, and proposals anyone can vote on. */
export function AtlasConstellationsPanel({ items, rule, active, me, signedIn, show, onShow, onPick, onVote, onPropose, onWithdraw, error }) {
  const official = items.filter((c) => c.status === "official");
  const proposed = items.filter((c) => c.status !== "official");
  const pct = Math.round((rule?.approve_share ?? 0.8) * 100);
  const row = (c) => {
    const total = c.yes + c.no;
    const share = total ? Math.round((100 * c.yes) / total) : 0;
    const mine = c.username && c.username === me;
    return (
      <div key={c.id} className={`rounded-xl border p-2.5 transition ${active === c.id ? "border-white/25 bg-white/[0.06]" : "border-white/5 hover:border-white/15"}`}>
        <button onClick={() => onPick(c)} className="flex w-full items-center justify-between gap-2 text-left">
          <span className="flex min-w-0 items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: c.color, boxShadow: `0 0 10px ${c.color}` }} />
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-white">{c.name}</span>
              <span className="block truncate text-[11px] text-gray-500">by {c.author} · {c.ids.length} stars</span>
            </span>
          </span>
          <span className={`shrink-0 text-xs ${c.status === "official" ? "text-sky-200" : "text-gray-400"}`}>{total ? `${share}% yes` : "no votes"}</span>
        </button>
        <div className="mt-2 h-1 w-full rounded-full bg-white/5" title={`${c.yes} yes · ${c.no} no`}>
          <div className="h-1 rounded-full" style={{ width: `${share}%`, background: c.color }} />
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]">
          {!mine && [[true, "👍 Yes"], [false, "👎 No"]].map(([up, label]) => (
            <button key={label} onClick={() => onVote(c, c.my_vote === up ? null : up)}
              className={`rounded-md border px-2 py-0.5 ${c.my_vote === up ? "border-sky-300/60 bg-sky-300/15 text-white" : "border-white/10 text-gray-300 hover:text-white"}`}>
              {label}
            </button>
          ))}
          <span className="text-gray-500">{c.yes} yes · {c.no} no</span>
          <span className="flex-1" />
          {mine
            ? <button onClick={() => onWithdraw(c)} className="text-gray-500 hover:text-rose-300">Take down</button>
            : <ReportButton kind="constellation" target={String(c.id)} label="report" className="text-gray-600 hover:text-rose-300" />}
        </div>
      </div>
    );
  };
  return (
    <>
      <p className="text-xs leading-5 text-gray-400">
        Shapes listeners drew across everyone&apos;s music. Propose one and people vote: with at least {rule?.min_votes ?? 5} votes
        and {pct}% saying yes, it becomes an official constellation that everyone sees on the atlas.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {signedIn
          ? <button onClick={onPropose} className="rounded-lg bg-gradient-to-r from-sky-500 to-indigo-500 px-3 py-1.5 text-xs font-semibold text-white hover:brightness-110">✦ Propose a constellation</button>
          : <Link href="/login?next=/atlas" className="rounded-lg border border-white/15 px-3 py-1.5 text-xs text-gray-200 hover:bg-white/10">Sign in to propose one</Link>}
        {official.length > 0 && (
          <label className="flex items-center gap-1.5 text-[11px] text-gray-400">
            <input type="checkbox" checked={show} onChange={(e) => onShow(e.target.checked)} className="accent-sky-400" /> Show on map
          </label>
        )}
      </div>
      {error && <p className="text-[11px] text-rose-300">{error}</p>}
      <div className="pt-1 text-[11px] uppercase tracking-wider text-gray-500">Official</div>
      {official.length ? official.map(row) : <p className="text-xs text-gray-500">None yet. Vote on the proposals below.</p>}
      <div className="pt-1 text-[11px] uppercase tracking-wider text-gray-500">Proposed: vote on them</div>
      {proposed.length ? proposed.map(row) : <p className="text-xs text-gray-500">No proposals right now.</p>}
    </>
  );
}
