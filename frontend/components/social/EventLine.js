import Link from "next/link";

import Avatar from "@/components/ui/Avatar";

export function ago(seconds) {
  const s = Date.now() / 1000 - seconds;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  if (s < 86400 * 14) return `${Math.round(s / 86400)} d ago`;
  return new Date(seconds * 1000).toLocaleDateString();
}

const fmt = (v) => (Array.isArray(v) ? v.join(", ") : typeof v === "number" && v <= 1 ? `${Math.round(v * 100)}/100` : String(v));

function Person({ username, name }) {
  if (!username) return <b className="text-gray-200">Someone</b>;
  return <Link href={`/u/${username}`} className="font-semibold text-white hover:underline">{name || username}</Link>;
}

/** One line of the feed or a profile's activity. `me`: the signed-in username (for "you"). */
export default function EventLine({ e, me }) {
  const d = e.data || {};
  const you = (u) => (u && u === me ? <b className="text-white">you</b> : <Person username={u} name={u === e.target ? e.target_name : e.actor_name} />);
  let icon = "✦";
  let text;
  switch (e.kind) {
    case "shared_map":
      icon = "🌌";
      text = <>{you(e.actor)} shared a map: <Link href={`/s/${d.id}`} className="text-fuchsia-200 hover:underline">{d.title}</Link>{d.songs ? <span className="text-gray-500"> · {d.songs.toLocaleString()} songs</span> : null}</>;
      break;
    case "followed":
      icon = "➕";
      text = <>{you(e.actor)} started following {you(e.target)}</>;
      break;
    case "upvoted":
      icon = "▲";
      text = <>{e.actor ? you(e.actor) : "Someone"} upvoted {e.target === me ? "your map" : "a map"} <Link href={`/s/${d.id}`} className="text-fuchsia-200 hover:underline">{d.title}</Link></>;
      break;
    case "compared":
      icon = "◐";
      text = <>{e.actor ? you(e.actor) : "Someone"} compared their taste with {e.target === me ? "your map" : "a map"} <Link href={`/s/${d.id}`} className="text-fuchsia-200 hover:underline">{d.title}</Link>{d.match != null ? <span className="text-emerald-300"> · {d.match}% match</span> : null}</>;
      break;
    case "fix_agreed":
      icon = "✓";
      text = <>Listeners agreed with your fix: <b className="text-white">{d.title}</b>{d.artist ? ` by ${d.artist}` : ""} · {d.label} {fmt(d.value)}. It&apos;s on everyone&apos;s maps now.</>;
      break;
    case "pinned":
      icon = "📌";
      text = <>{you(e.actor)} pinned a note on <Link href="/atlas" className="text-fuchsia-200 hover:underline">{d.title || "a song"}</Link>: <span className="text-gray-300">&ldquo;{d.text}&rdquo;</span></>;
      break;
    case "proposed_constellation":
      icon = "✦";
      text = <>{you(e.actor)} proposed a constellation on the atlas: <Link href={`/atlas?constellation=${d.id}`} className="text-sky-200 hover:underline">{d.name}</Link>. Vote on it!</>;
      break;
    case "artist_track":
      icon = "🎤";
      text = <>{you(e.actor)} put a new track on the atlas: <b className="text-white">{d.title}</b>{d.galaxy ? <> in <span className="text-fuchsia-200">{d.galaxy}</span></> : null}</>;
      break;
    default:
      text = <>{you(e.actor)} did something</>;
  }
  return (
    <div className="flex gap-3 py-3">
      {e.actor ? <Avatar name={e.actor_name} username={e.actor} size={34} /> : (
        <span className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-full bg-white/5 text-sm">{icon}</span>
      )}
      <div className="min-w-0 flex-1">
        <div className="text-sm leading-6 text-gray-400">{text}</div>
        <div className="text-[11px] text-gray-600">{ago(e.at)}</div>
      </div>
    </div>
  );
}
