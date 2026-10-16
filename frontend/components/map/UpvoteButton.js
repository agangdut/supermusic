import { useState } from "react";

import { voteSharedMap } from "@/lib/api";
import { setMapVote, useMapVote } from "@/lib/mapVotes";

/** ▲ count. Click to upvote a shared map, click again to take it back. Every button for the
 *  same map, on any page or tab, shows the same count (see lib/mapVotes.js).
 *  `check`: the page was drawn on the server, so ask who is looking before trusting `voted`. */
export default function UpvoteButton({ id, votes = 0, voted = false, size = "md", check = false, onChange }) {
  const state = useMapVote(id, votes, voted, { check });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const click = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (busy) return;
    const before = state;
    const up = !state.voted;
    setBusy(true);
    setError(null);
    setMapVote(id, Math.max(0, before.votes + (up ? 1 : -1)), up); // show it straight away, everywhere
    try {
      const r = await voteSharedMap(id, up);
      setMapVote(id, r.votes, r.voted);
      onChange?.(r);
    } catch (err) {
      setMapVote(id, before.votes, before.voted); // put it back
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const big = size === "lg";
  return (
    <span className="inline-flex flex-col items-center">
      <button onClick={click} title={error || (state.voted ? "Take your upvote back" : "Upvote this map")}
        aria-pressed={state.voted}
        className={`flex items-center gap-1.5 rounded-lg border font-semibold tabular-nums transition ${
          big ? "px-3 py-1.5 text-sm" : "px-2 py-1 text-xs"
        } ${state.voted
          ? "border-fuchsia-400/60 bg-fuchsia-500/20 text-fuchsia-100"
          : "border-white/15 bg-black/30 text-gray-300 hover:border-fuchsia-400/50 hover:text-white"}`}>
        <span className={state.voted ? "text-fuchsia-300" : ""}>▲</span>
        {state.votes}
      </button>
      {error && <span className="mt-1 max-w-[160px] text-center text-[10px] leading-4 text-rose-300">{error}</span>}
    </span>
  );
}
