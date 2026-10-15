// Signing in: the account token lives in this browser (localStorage) and every API call
// sends it (utils/fetcher.js). Components read the signed-in user with useAuth().
import { useEffect, useState } from "react";

import { apiFetch } from "@/utils/fetcher";

const TOKEN = "sm-token";
const USER = "sm-user";
const listeners = new Set();

function read(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key, value) {
  try {
    if (value == null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // private window: signed in until the tab closes
  }
}

let state = { token: null, user: null, ready: false };

function load() {
  if (typeof window === "undefined" || state.ready) return;
  let user = null;
  try {
    user = JSON.parse(read(USER) || "null");
  } catch {
    user = null;
  }
  state = { token: read(TOKEN), user, ready: true };
}

function set(next) {
  state = { ...state, ...next, ready: true };
  write(TOKEN, state.token);
  write(USER, state.user ? JSON.stringify(state.user) : null);
  listeners.forEach((fn) => fn(state));
}

export function authToken() {
  load();
  return state.token;
}

/** Maps shared from this browser before signing in move onto the account. */
async function claimBrowserShares() {
  let mine = [];
  try {
    mine = JSON.parse(read("supermusic.mySharedMaps") || "[]");
  } catch {
    mine = [];
  }
  if (!mine.length) return;
  try {
    await apiFetch("/auth/claim-shares", {
      method: "POST",
      body: JSON.stringify({ shares: mine.map((s) => ({ id: s.id, delete_token: s.delete_token })) }),
    });
  } catch {
    // they stay deletable from this browser either way
  }
}

/** After signing in, the map this browser last built becomes the account's own map. */
async function syncMyMap() {
  try {
    const m = JSON.parse(read("sm-my-map") || "null");
    if (m?.csv_path) await apiFetch("/me/library", { method: "PUT", body: JSON.stringify({ csv_path: m.csv_path, title: m.title }) });
  } catch {
    // the import may be from before a server reset; nothing to sync
  }
}

async function start(path, body) {
  const r = await apiFetch(path, { method: "POST", body: JSON.stringify(body) });
  set({ token: r.access_token, user: r.user });
  await Promise.all([claimBrowserShares(), syncMyMap()]);
  return r.user;
}

export const signIn = (username, password) => start("/auth/login", { username, password });
export const signUp = (username, password, display_name) => start("/auth/register", { username, password, display_name: display_name || null });

export function signOut() {
  set({ token: null, user: null });
}

export async function refreshMe() {
  load();
  if (!state.token) return null;
  try {
    const user = await apiFetch("/auth/me");
    set({ user });
    return user;
  } catch (e) {
    if (/401|Sign in|Authentication/i.test(e.message || "")) set({ token: null, user: null });
    return state.user;
  }
}

export function updateUser(user) {
  set({ user });
}

/** { user, token, ready }: re-renders when someone signs in or out (in any tab). */
export function useAuth() {
  const [s, setS] = useState({ token: null, user: null, ready: false });
  useEffect(() => {
    load();
    setS(state);
    const fn = (next) => setS(next);
    listeners.add(fn);
    const onStorage = (e) => {
      if (e.key === TOKEN || e.key === USER) {
        state = { ...state, ready: false };
        load();
        fn(state);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => {
      listeners.delete(fn);
      window.removeEventListener("storage", onStorage);
    };
  }, []);
  return s;
}
