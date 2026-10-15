// "Your library in numbers": the map's library-wide statistics (backend: app/core/map_stats.py).
import { useState } from "react";
import { colorFor } from "./colors";

const pct = (v) => (v == null ? "–" : `${v < 0.01 && v > 0 ? "<1" : Math.round(v * 100)}%`);
const LIB = "#64748b"; // library share
const PLAY = "#e879f9"; // listening share

function Card({ title, sub, children, className = "" }) {
  return (
    <section className={`rounded-xl border border-white/10 bg-white/[0.02] p-4 ${className}`}>
      <h3 className="text-sm font-semibold text-white">{title}</h3>
      {sub && <p className="mt-0.5 text-[11px] leading-5 text-gray-500">{sub}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Tile({ value, label }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5">
      <div className="text-xl font-semibold tabular-nums text-white">{value}</div>
      <div className="text-[11px] text-gray-500">{label}</div>
    </div>
  );
}

function Legend({ listening }) {
  return (
    <div className="mb-2 flex gap-3 text-[11px] text-gray-400">
      <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ background: LIB }} /> share of songs</span>
      {listening && <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ background: PLAY }} /> share of plays</span>}
    </div>
  );
}

// Two thin bars per row: how much of the library vs how much of the listening
function ShareRows({ rows, max, extra }) {
  const top = max || Math.max(...rows.map((r) => Math.max(r.library_share, r.listening_share ?? 0)), 0.01);
  return (
    <div className="space-y-2">
      {rows.map((r) => {
        const tip = `${r.name}: ${r.songs.toLocaleString()} songs (${pct(r.library_share)})` +
          (r.listening_share != null ? `, ${pct(r.listening_share)} of plays` : "") +
          (r.skip_rate != null ? `, skipped ${pct(r.skip_rate)} of the time` : "");
        return (
          <div key={r.name} title={tip} className="grid grid-cols-[96px_1fr_auto] items-center gap-2 text-xs">
            <span className="truncate text-gray-300">{r.name}</span>
            <div className="space-y-0.5">
              <div className="h-1.5 rounded-r" style={{ width: `${(r.library_share / top) * 100}%`, background: LIB, minWidth: 2 }} />
              {r.listening_share != null && (
                <div className="h-1.5 rounded-r" style={{ width: `${(r.listening_share / top) * 100}%`, background: PLAY, minWidth: 2 }} />
              )}
            </div>
            <span className="w-16 text-right tabular-nums text-gray-400">{extra ? extra(r) : pct(r.listening_share ?? r.library_share)}</span>
          </div>
        );
      })}
    </div>
  );
}

// Vertical bars over an ordered axis (decades, tempo): song share, with the play share as a marker
function Columns({ rows, listening }) {
  const top = Math.max(...rows.map((r) => Math.max(r.library_share, r.listening_share ?? 0)), 0.01);
  return (
    <div>
      <div className="flex h-28 items-end gap-0.5">
        {rows.map((r) => (
          <div key={r.name} className="relative flex h-full flex-1 items-end"
            title={`${r.name}: ${r.songs.toLocaleString()} songs (${pct(r.library_share)})${r.listening_share != null ? `, ${pct(r.listening_share)} of plays` : ""}`}>
            <div className="w-full rounded-t" style={{ height: `${(r.library_share / top) * 100}%`, background: LIB, minHeight: 2 }} />
            {listening && r.listening_share != null && (
              <div className="absolute left-0 right-0 h-0.5 rounded" style={{ bottom: `${(r.listening_share / top) * 100}%`, background: PLAY }} />
            )}
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-gray-500">
        <span>{rows[0]?.name}</span><span>{rows[rows.length - 1]?.name}</span>
      </div>
    </div>
  );
}

// Camelot wheel as a 2 x 12 grid: brighter = more songs; the number is how much more you play it than its share
function KeyGrid({ keys, listening }) {
  const top = Math.max(...keys.map((k) => k.library_share), 0.01);
  const by = Object.fromEntries(keys.map((k) => [k.camelot, k]));
  return (
    <div className="space-y-1">
      {["B", "A"].map((ring) => (
        <div key={ring} className="grid grid-cols-12 gap-0.5">
          {Array.from({ length: 12 }, (_, i) => {
            const k = by[`${i + 1}${ring}`];
            const lift = k && listening && k.listening_share != null && k.library_share > 0 ? k.listening_share / k.library_share : null;
            return (
              <div key={i} className="grid aspect-square place-items-center rounded text-[9px] text-white/80"
                style={{ background: k ? `rgba(167,139,250,${0.08 + 0.8 * (k.library_share / top)})` : "rgba(255,255,255,0.03)" }}
                title={k ? `${k.name} (${k.camelot}): ${k.songs} songs${lift ? `, played ${lift.toFixed(1)}× its share` : ""}` : `${i + 1}${ring}: none`}>
                {k?.name}
              </div>
            );
          })}
        </div>
      ))}
      <div className="flex justify-between text-[10px] text-gray-500"><span>top row: major keys</span><span>bottom: minor</span></div>
    </div>
  );
}

// Songs that entered your library per year/month, split by map cluster
function Timeline({ timeline, clusters }) {
  const periods = timeline.periods;
  const top = Math.max(...periods.map((p) => p.new_songs), 1);
  const names = Object.fromEntries(clusters.map((c) => [String(c.id), c.label.split(" · ")[0]]));
  return (
    <div>
      <div className="flex h-32 items-end gap-0.5">
        {periods.map((p) => (
          <div key={p.period} className="flex h-full flex-1 flex-col justify-end"
            title={`${p.period}: ${p.new_songs.toLocaleString()} new songs${p.top_genre ? `, mostly ${p.top_genre}` : ""}\n` +
              Object.entries(p.clusters).slice(0, 4).map(([c, v]) => `${names[c] || "Cluster " + c}: ${v}`).join("\n")}>
            {Object.entries(p.clusters).map(([c, v]) => (
              <div key={c} style={{ height: `${(v / top) * 100}%`, background: colorFor(Number(c)), minHeight: v ? 1 : 0 }} className="w-full border-t border-[#0b1121]" />
            ))}
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-gray-500">
        <span>{periods[0]?.period}</span><span>{periods[periods.length - 1]?.period}</span>
      </div>
    </div>
  );
}

const LISTS = [
  { id: "rediscover", label: "Rediscover", hint: "Songs you played a lot, but not in the last year of your history.", sub: (x) => `${x.plays} plays · last ${x.last_played}` },
  { id: "skipped", label: "Keep skipping", hint: "Skipped at least half the times they came on. Candidates to drop from playlists.", sub: (x) => `skipped ${x.skips} of ${x.skips + x.plays}` },
  { id: "unusual", label: "Odd ones out", hint: "Songs furthest from everything else in your library: your outliers.", sub: null },
  { id: "never_played", label: "Never played", hint: "In your library or playlists, but not once in your listening history.", sub: null },
];

function Lists({ lists, byId, onSelect }) {
  const have = LISTS.filter((l) => lists[l.id]?.length);
  const [tab, setTab] = useState(have[0]?.id);
  const cur = have.find((l) => l.id === tab) || have[0];
  if (!cur) return null;
  return (
    <Card title="Worth a look" sub={cur.hint}>
      <div className="mb-3 flex flex-wrap gap-1">
        {have.map((l) => (
          <button key={l.id} onClick={() => setTab(l.id)}
            className={`rounded-md px-2 py-1 text-xs ${l.id === cur.id ? "bg-white/10 text-white" : "text-gray-400 hover:text-gray-200"}`}>
            {l.label} <span className="text-gray-500">{lists[l.id].length}</span>
          </button>
        ))}
      </div>
      <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
        {lists[cur.id].map((x) => {
          const t = byId[x.id];
          if (!t) return null;
          return (
            <button key={x.id} onClick={() => onSelect(x.id)} className="group flex items-start gap-2 text-left">
              <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: colorFor(t.cluster) }} />
              <span className="min-w-0">
                <span className="block truncate text-sm text-gray-100 group-hover:text-white">{t.title}</span>
                <span className="block truncate text-xs text-gray-500">
                  {[t.artist, cur.sub ? cur.sub(x) : t.genre].filter(Boolean).join(" · ")}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </Card>
  );
}

export default function StatsPanel({ stats, clusters, byId, onSelect }) {
  if (!stats) return null;
  const o = stats.overview || {};
  const listening = o.plays > 0 || stats.genres?.some((g) => g.listening_share != null);
  const c = stats.concentration;
  const d = stats.diversity;
  return (
    <div className="mt-6 space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-white">Your library in numbers</h2>
        <p className="text-xs text-gray-500">Hover a bar for exact numbers. Click a song to find it on the map.</p>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        <Tile value={o.songs?.toLocaleString()} label="songs" />
        <Tile value={o.artists?.toLocaleString()} label="artists" />
        {o.plays != null && <Tile value={o.plays.toLocaleString()} label="plays" />}
        {o.hours != null && <Tile value={Math.round(o.hours).toLocaleString()} label="hours listened" />}
        {o.liked != null && <Tile value={o.liked.toLocaleString()} label="liked" />}
        {o.never_played != null && <Tile value={o.never_played.toLocaleString()} label="never played" />}
        {o.first_date && <Tile value={`${o.first_date.slice(0, 4)}–${o.last_date.slice(0, 4)}`} label="years of history" />}
      </div>

      {(c || d) && (
        <div className="grid gap-4 md:grid-cols-2">
          {c && (
            <Card title="How concentrated your listening is">
              <p className="text-sm leading-6 text-gray-300">
                Half of all your plays come from just <b className="text-white">{c.half_plays_songs.toLocaleString()}</b> song{c.half_plays_songs === 1 ? "" : "s"}.
                Your top 1% of songs get <b className="text-white">{pct(c.top_1pct_share)}</b> of plays, your top 10% get <b className="text-white">{pct(c.top_10pct_share)}</b>.
              </p>
            </Card>
          )}
          {d && d.library != null && (
            <Card title="How varied it is" sub="0% = all one genre, 100% = spread evenly over every genre you have.">
              <div className="flex gap-6 text-sm text-gray-300">
                <div><div className="text-2xl font-semibold text-white">{pct(d.library)}</div>your library</div>
                {d.listening != null && <div><div className="text-2xl font-semibold text-white">{pct(d.listening)}</div>what you play</div>}
                <div><div className="text-2xl font-semibold text-white">{d.genres}</div>genres</div>
              </div>
              {d.listening != null && (
                <p className="mt-2 text-xs text-gray-500">
                  {d.listening < d.library - 0.05 ? "You play a narrower slice than you collect." :
                    d.listening > d.library + 0.05 ? "You play more widely than your library's mix suggests." :
                      "What you play is about as varied as what you collect."}
                </p>
              )}
            </Card>
          )}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        {stats.genres?.length > 0 && (
          <Card title="Genres" sub={listening ? "Right column: share of plays (and skip rate on hover)." : null}>
            <Legend listening={listening} />
            <ShareRows rows={stats.genres} />
          </Card>
        )}
        {stats.top_artists?.length > 0 && (
          <Card title={listening ? "Top artists by plays" : "Artists with the most songs"}>
            <Legend listening={listening} />
            <ShareRows rows={stats.top_artists} />
          </Card>
        )}
        {stats.keys?.length > 0 && (
          <Card title="Keys (Camelot wheel)" sub="Brighter = more songs. Neighbouring columns mix well together.">
            <KeyGrid keys={stats.keys} listening={listening} />
            {stats.modes?.length === 2 && (
              <p className="mt-3 text-xs text-gray-400">
                {stats.modes.map((m) => `${pct(m.library_share)} ${m.name}`).join(" · ")}
                {listening && stats.modes[0].listening_share != null && ` (plays: ${stats.modes.map((m) => `${pct(m.listening_share)} ${m.name}`).join(" · ")})`}
              </p>
            )}
          </Card>
        )}
        {stats.decades?.length > 1 && (
          <Card title="Release decades">
            <Legend listening={listening} />
            <Columns rows={stats.decades} listening={listening} />
          </Card>
        )}
        {stats.tempo?.length > 1 && (
          <Card title="Tempo (BPM)">
            <Legend listening={listening} />
            <Columns rows={stats.tempo} listening={listening} />
          </Card>
        )}
        {stats.timeline?.periods?.length > 1 && (
          <Card title={`New songs per ${stats.timeline.by}`} sub="Coloured by map cluster, so you can see your taste drift over time.">
            <Timeline timeline={stats.timeline} clusters={clusters} />
          </Card>
        )}
      </div>

      {stats.lists && <Lists lists={stats.lists} byId={byId} onSelect={onSelect} />}
    </div>
  );
}
