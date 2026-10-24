// Black holes: songs that hold a big share of all the plays on a map.
// Maps without play counts (title/artist-only imports) simply have none.

// A song becomes a black hole when it has at least this share of the map's total plays...
export const BLACK_HOLE_SHARE = 0.02;
// ...and at least this many times the plays of an average played song. On a small map
// (the 150-song sample) lots of songs pass 2%; this keeps black holes for real outliers.
export const BLACK_HOLE_LIFT = 8;
// Never more than this many per map, so they stay special
export const MAX_BLACK_HOLES = 5;

// Map of track id -> share of all plays (0..1), biggest first
export function findBlackHoles(tracks) {
  const out = new Map();
  if (!tracks?.length) return out;
  const plays = (t) => (typeof t.plays === "number" && t.plays > 0 ? t.plays : 0);
  let total = 0, played = 0;
  for (const t of tracks) if (plays(t)) { total += plays(t); played += 1; }
  if (!total) return out;
  const min = Math.max(total * BLACK_HOLE_SHARE, (total / played) * BLACK_HOLE_LIFT);
  tracks
    .filter((t) => plays(t) >= min)
    .sort((a, b) => plays(b) - plays(a))
    .slice(0, MAX_BLACK_HOLES)
    .forEach((t) => out.set(t.id, plays(t) / total));
  return out;
}

export const sharePct = (s) => `${(s * 100).toFixed(s < 0.1 ? 1 : 0)}%`;
