import { useEffect, useState } from "react";

import { voteSharedMap } from "@/lib/api";

/** ▲ count. Click to upvote a shared map, click again to take it back. */
export default function UpvoteButton({ id, votes = 0, voted = false, size = "md", onChange }) {
  const [state, setState] = useState({ votes, voted });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => setState({ votes, voted }), [votes, voted]);

  const click = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (busy) return;
    const up = !state.voted;
    setBusy(true);
    setError(null);
    setState((s) => ({ votes: s.votes + (up ? 1 : -1), voted: up })); // show it straight away
    try {
      const r = await voteSharedMap(id, up);
      setState(r);
      onChange?.(r);
    } catch (err) {
      setState({ votes, voted }); // put it back
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
