// Map Radio: turn a spot on the map into an ordered station.
//
// Songs that sound alike sit close together on the map, so a station is a walk through
// the stars: each next song is one of the closest unplayed ones, so the music drifts
// gradually instead of jumping. Three kinds:
//   song     songs around one song, spreading outwards
//   cluster  a walk through one cluster
//   journey  from one song to another, a DJ-style path across the map
import { clusterName } from "./colors";

const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);

// Small seeded random generator, so "Shuffle" gives a new order but the same seed repeats
function rng(seed) {
  let s = seed >>> 0 || 1;
  return () => {
    s ^= s << 13; s ^= s >>> 17; s ^= s << 5;
    return ((s >>> 0) % 1e6) / 1e6;
  };
}

const artistOf = (t) => (t.artist || "").toLowerCase();

// The same artist twice in a row, or too often, makes a station feel stuck
function allowed(t, picked, perArtist, maxPerArtist) {
  const a = artistOf(t);
  if (!a) return true;
  if (picked.length && artistOf(picked[picked.length - 1]) === a) return false;
  return (perArtist.get(a) || 0) < maxPerArtist;
}

function walk(start, pool, length, random, target = null) {
  const picked = [start];
  const used = new Set([start.id]);
  const perArtist = new Map([[artistOf(start), 1]]);
  const maxPerArtist = Math.max(2, Math.ceil(length / 8));
  while (picked.length < length) {
    const here = picked[picked.length - 1];
    // Journeys aim at a point a little further along the line to the target
    let aim = here;
    if (target) {
      const k = 1 / Math.max(1, length - picked.length);
      aim = { x: here.x + (target.x - here.x) * k, y: here.y + (target.y - here.y) * k, z: here.z + (target.z - here.z) * k };
    }
    const options = [];
    for (const t of pool) {
      if (used.has(t.id) || (target && t.id === target.id)) continue;
      options.push([dist(aim, t), t]);
    }
    if (!options.length) break;
    options.sort((a, b) => a[0] - b[0]);
    const fits = options.filter(([, t]) => allowed(t, picked, perArtist, maxPerArtist));
    const near = (fits.length ? fits : options).slice(0, 4);
    // Mostly the closest, sometimes the 2nd-4th closest
    const r = random();
    const next = near[r < 0.55 ? 0 : Math.min(near.length - 1, 1 + Math.floor((r - 0.55) / 0.15))][1];
    picked.push(next);
    used.add(next.id);
    perArtist.set(artistOf(next), (perArtist.get(artistOf(next)) || 0) + 1);
  }
  if (target && picked[picked.length - 1].id !== target.id) {
    if (picked.length >= length) picked.pop();
    picked.push(target);
  }
  return picked;
}

/** Build a station. Returns { kind, name, ids }. */
export function buildStation(data, { kind, seedId, clusterId, toId, length = 25, seed = 1 }) {
  const tracks = data?.tracks || [];
  const byId = new Map(tracks.map((t) => [t.id, t]));
  const random = rng(seed);
  if (kind === "cluster") {
    const members = tracks.filter((t) => t.cluster === clusterId);
    if (!members.length) return null;
    // Start at a well-loved song near the middle of the cluster
    const c = ["x", "y", "z"].reduce((o, k) => ({ ...o, [k]: members.reduce((a, t) => a + t[k], 0) / members.length }), {});
    const ranked = [...members].sort((a, b) => (b.engagement || 0) - (a.engagement || 0) || dist(a, c) - dist(b, c));
    const start = ranked[Math.floor(random() * Math.min(5, ranked.length))];
    const cl = data.clusters.find((x) => x.id === clusterId);
    return { kind, name: `${clusterName(cl)} radio`, ids: walk(start, members, length, random).map((t) => t.id) };
  }
  const start = byId.get(seedId);
  if (!start) return null;
  if (kind === "journey") {
    const end = byId.get(toId);
    if (!end || end.id === start.id) return null;
    // Only songs near the straight line between the two are candidates
    const span = dist(start, end) || 1;
    const pool = tracks.filter((t) => {
      const along = ((t.x - start.x) * (end.x - start.x) + (t.y - start.y) * (end.y - start.y) + (t.z - start.z) * (end.z - start.z)) / span;
      return along > -span * 0.1 && along < span * 1.1;
    });
    return { kind, name: `${start.title} → ${end.title}`, ids: walk(start, pool, length, random, end).map((t) => t.id) };
  }
  // Song radio: the closest few hundred songs are plenty to walk through
  const pool = [...tracks].sort((a, b) => dist(a, start) - dist(b, start)).slice(0, Math.max(length * 4, 60));
  return { kind: "song", name: `${start.title} radio`, ids: walk(start, pool, length, random).map((t) => t.id) };
}
