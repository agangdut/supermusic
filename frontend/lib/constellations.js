// Song constellations: stars on a Music Map joined by lines into a named shape.
//
// A constellation keeps its songs by artist and title, not by star number: a re-import or a
// Remap gives every song a new number, but "Artist · Title" stays the same, so the shape
// comes back. Where they are kept:
//   your own map, signed in   -> your account (GET/PUT /me/constellations), so every device sees them
//   your own map, signed out  -> this browser (localStorage)
//   the sample map            -> this browser, so anyone can try it
//   someone's shared map      -> inside the share, read-only (they travel with the map)
import { useCallback, useEffect, useMemo, useState } from "react";

import { apiFetch } from "@/utils/fetcher";

export const MAX_STARS = 40;
export const MAX_CONSTELLATIONS = 30;
export const NAME_MAX = 40;
export const CONSTELLATION_COLORS = ["#7dd3fc", "#fde68a", "#f9a8d4", "#86efac", "#c4b5fd", "#fdba74", "#f87171", "#e5e7eb"];

const norm = (s) => String(s || "").trim().toLowerCase();
export const songKey = (t) => `${norm(t.artist)}|${norm(t.title)}`;
export const starOf = (t) => ({ artist: t.artist || "", title: t.title });
export const newId = () => Math.random().toString(36).slice(2, 10);

/** Turn saved songs back into star numbers on this map. Songs that aren't on it are skipped. */
export function resolveConstellations(list, tracks) {
  if (!list?.length || !tracks?.length) return [];
  const ids = new Map();
  for (const t of tracks) if (!ids.has(songKey(t))) ids.set(songKey(t), t.id);
  return list
    .map((c) => {
      const found = c.stars.map((s) => ids.get(songKey(s))).filter((id) => id != null);
      return { ...c, ids: found, missing: c.stars.length - found.length };
    })
    .filter((c) => c.ids.length >= 2);
}

const localKey = (where) => `sm-constellations:${where}`;

function readLocal(where) {
  try {
    const v = JSON.parse(window.localStorage.getItem(localKey(where)) || "[]");
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

function writeLocal(where, list) {
  try {
    window.localStorage.setItem(localKey(where), JSON.stringify(list));
  } catch {
    // private window: they last until the tab closes
  }
}

/**
 * The constellations for the map on screen.
 * where: "mine" | "sample" | "shared" | null (compare: none). `shared` is the shared map's list.
 * Returns { list, editable, save(list), error }.
 */
export function useConstellations({ where, user, shared }) {
  const [list, setList] = useState([]);
  const [error, setError] = useState(null);
  const signedIn = !!user?.username;

  useEffect(() => {
    setError(null);
    if (where === "shared") { setList(shared || []); return undefined; }
    if (!where) { setList([]); return undefined; }
    const local = readLocal(where);
    setList(local);
    if (where !== "mine" || !signedIn) return undefined;
    let live = true;
    apiFetch("/me/constellations")
      .then(async (r) => {
        if (!live) return;
        let saved = r.constellations || [];
        // First time signed in on this browser: move what was drawn here onto the account
        if (!saved.length && local.length) {
          saved = (await apiFetch("/me/constellations", { method: "PUT", body: JSON.stringify({ constellations: local }) })).constellations;
        }
        if (!live) return;
        setList(saved);
        writeLocal(where, saved);
      })
      .catch(() => {}); // offline or signed out elsewhere: the browser's copy still shows
    return () => { live = false; };
  }, [where, signedIn, shared]);

  const save = useCallback(async (next) => {
    setList(next);
    setError(null);
    if (!where || where === "shared") return;
    writeLocal(where, next);
    if (where === "mine" && signedIn) {
      try {
        await apiFetch("/me/constellations", { method: "PUT", body: JSON.stringify({ constellations: next }) });
      } catch (e) {
        setError(`Saved in this browser only: ${e.message || e}`);
      }
    }
  }, [where, signedIn]);

  return useMemo(() => ({ list, editable: where === "mine" || where === "sample", save, error }), [list, where, save, error]);
}
