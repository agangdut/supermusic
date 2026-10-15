// "Save to Spotify": create a playlist in the listener's own Spotify account.
//
// Runs entirely in the browser with Spotify's PKCE sign-in, so there is no secret to
// keep on the server. It needs a free Spotify app (developer.spotify.com/dashboard) with:
//   NEXT_PUBLIC_SPOTIFY_CLIENT_ID   its Client ID
//   redirect URI                    <this site>/spotify-callback, e.g. http://127.0.0.1:3000/spotify-callback
//                                   (Spotify no longer accepts "localhost"; use 127.0.0.1)
// While the app is in Spotify's development mode, only its owner (who needs Premium) and up
// to 5 people added under "User Management" can sign in. See docs/music-map.md.

export const SPOTIFY_CLIENT_ID = process.env.NEXT_PUBLIC_SPOTIFY_CLIENT_ID || "";
const SCOPES = "playlist-modify-private playlist-modify-public";
const PENDING = "supermusic.spotifyPending";

const redirectUri = () => `${window.location.origin}/spotify-callback`;

function base64url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** Remember the playlist, then send the listener to Spotify to sign in. */
export async function startSpotifySave({ name, description, songs, back }) {
  const verifier = base64url(crypto.getRandomValues(new Uint8Array(48)));
  const challenge = base64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
  const state = base64url(crypto.getRandomValues(new Uint8Array(12)));
  sessionStorage.setItem(PENDING, JSON.stringify({ verifier, state, name, description, songs, back }));
  const q = new URLSearchParams({
    client_id: SPOTIFY_CLIENT_ID,
    response_type: "code",
    redirect_uri: redirectUri(),
    scope: SCOPES,
    code_challenge_method: "S256",
    code_challenge: challenge,
    state,
  });
  window.location.assign(`https://accounts.spotify.com/authorize?${q}`);
}

export function pendingSave() {
  try {
    return JSON.parse(sessionStorage.getItem(PENDING) || "null");
  } catch {
    return null;
  }
}

export function clearPendingSave() {
  sessionStorage.removeItem(PENDING);
}

async function api(token, path, options = {}) {
  for (let attempt = 0; ; attempt++) {
    const r = await fetch(`https://api.spotify.com/v1${path}`, {
      ...options,
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...(options.headers || {}) },
    });
    if (r.status === 429 && attempt < 3) {
      // Rate limited: wait as long as Spotify asks
      await new Promise((ok) => setTimeout(ok, (Number(r.headers.get("Retry-After")) || 2) * 1000));
      continue;
    }
    if (r.status === 403) throw new Error("Spotify refused. While the Spotify app is in development mode, only accounts added under User Management in its dashboard can use it.");
    if (!r.ok) throw new Error(`Spotify said ${r.status}: ${(await r.text()).slice(0, 200)}`);
    return r.status === 204 ? null : r.json();
  }
}

const trackUri = (url) => {
  const m = /open\.spotify\.com\/(?:intl-[a-z-]+\/)?track\/([A-Za-z0-9]{22})/.exec(url || "");
  return m ? `spotify:track:${m[1]}` : null;
};

/** Back from Spotify's sign-in: swap the code for a token and build the playlist. */
export async function finishSpotifySave({ code, state }, onProgress = () => {}) {
  const p = pendingSave();
  if (!p) throw new Error("Nothing to save: start again from the Music Map.");
  if (state !== p.state) throw new Error("The Spotify sign-in didn't match this browser. Please try again.");
  const r = await fetch("https://accounts.spotify.com/api/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
      redirect_uri: redirectUri(),
      client_id: SPOTIFY_CLIENT_ID,
      code_verifier: p.verifier,
    }),
  });
  if (!r.ok) throw new Error(`Spotify sign-in failed (${r.status}). Check the redirect URI in the Spotify app settings.`);
  const { access_token: token } = await r.json();

  // Songs without a Spotify link in the library are searched for by title and artist
  const uris = [];
  const missing = [];
  for (const [i, s] of p.songs.entries()) {
    onProgress(`Finding songs on Spotify… ${i + 1} of ${p.songs.length}`);
    let uri = trackUri(s.spotify_url);
    if (!uri) {
      const q = [s.title && `track:${s.title}`, s.artist && `artist:${s.artist}`].filter(Boolean).join(" ");
      const found = await api(token, `/search?${new URLSearchParams({ q, type: "track", limit: "1" })}`);
      uri = found?.tracks?.items?.[0]?.uri || null;
    }
    if (uri) uris.push(uri);
    else missing.push(s);
  }
  if (!uris.length) throw new Error("None of these songs were found on Spotify.");

  onProgress("Creating the playlist…");
  const playlist = await api(token, "/me/playlists", {
    method: "POST",
    body: JSON.stringify({ name: p.name.slice(0, 100), description: (p.description || "").slice(0, 300), public: false }),
  });
  for (let i = 0; i < uris.length; i += 100) {
    await api(token, `/playlists/${playlist.id}/items`, { method: "POST", body: JSON.stringify({ uris: uris.slice(i, i + 100) }) });
  }
  clearPendingSave();
  return { url: playlist.external_urls?.spotify, added: uris.length, missing, back: p.back };
}
