// One shared record of each map's upvotes, so every upvote button for the same map
// (Explore's top card and grid, "Shared from this browser", the map banner, the share
// page, profiles) shows the same count, and so do other open tabs of the site.
import { useEffect, useRef, useState } from "react";

import { getSharedMapVotes } from "@/lib/api";

const known = new Map(); // id -> { votes, voted, at }  (at: when this browser last voted on it)
const subscribers = new Set();
const RECENT_MS = 5000; // a list fetched just before a vote mustn't undo it when it lands

let channel = null;
function getChannel() {
  if (channel || typeof window === "undefined" || !("BroadcastChannel" in window)) return channel;
  channel = new BroadcastChannel("supermusic-map-votes");
  channel.onmessage = (e) => {
    const { id, votes, voted } = e.data || {};
    if (id) put(id, { votes, voted, at: Date.now() }, false);
  };
  return channel;
}

function put(id, value, broadcast) {
  known.set(id, value);
  subscribers.forEach((fn) => fn(id, value));
  if (broadcast) getChannel()?.postMessage({ id, votes: value.votes, voted: value.voted });
}

/** A vote made here: every button for this map, in every tab, shows it. */
export function setMapVote(id, votes, voted) {
  put(id, { votes, voted, at: Date.now() }, true);
}

/** Server numbers (a fresh list or page). Ignored right after a vote here, which is newer. */
export function seedMapVote(id, votes, voted) {
  const cur = known.get(id);
  if (cur && Date.now() - cur.at < RECENT_MS) return;
  if (cur && cur.votes === votes && cur.voted === voted) return;
  put(id, { votes, voted, at: cur?.at || 0 }, false);
}

/** Run fn(id, { votes, voted }) whenever any map's upvotes change. Returns an unsubscribe. */
export function onMapVote(fn) {
  getChannel();
  subscribers.add(fn);
  return () => subscribers.delete(fn);
}

/** This map's { votes, voted }, kept in step with every other button for it.
 *  `check`: ask the server who is looking (pages rendered on the server can't know). */
export function useMapVote(id, votes = 0, voted = false, { check = false } = {}) {
  const [state, setState] = useState(() => {
    const k = known.get(id);
    return k ? { votes: k.votes, voted: k.voted } : { votes, voted };
  });
  useEffect(() => onMapVote((changed, v) => { if (changed === id) setState({ votes: v.votes, voted: v.voted }); }), [id]);
  // New numbers from the server (a page opened or a list refreshed) reach every button
  const first = useRef(true);
  useEffect(() => {
    if (check && first.current) {
      first.current = false;
      getSharedMapVotes(id).then((r) => seedMapVote(id, r.votes, r.voted)).catch(() => {});
      const k = known.get(id);
      if (k) setState({ votes: k.votes, voted: k.voted });
      return;
    }
    first.current = false;
    seedMapVote(id, votes, voted);
    const k = known.get(id);
    if (k) setState({ votes: k.votes, voted: k.voted });
  }, [id, votes, voted, check]);
  return state;
}
