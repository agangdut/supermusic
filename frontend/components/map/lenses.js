// "Colour by" lenses for the Music Map: the same stars, coloured by one property at a time.
// Shared by the page (legend) and the 3D view (star colours).
import { CLUSTER_COLORS, colorFor } from "./colors";

const MISSING = "#3b4252"; // songs without the value stay visible but recede

// One hue from dim to bright, so "more" reads as "brighter" on the dark map
const RAMP = ["#1e3a8a", "#2563eb", "#38bdf8", "#a5f3fc", "#f0fdff"];

const year = (d) => (d ? Number(String(d).slice(0, 4)) + (Number(String(d).slice(5, 7)) || 1) / 12 - 1 / 12 : null);

export const LENSES = [
  { id: "cluster", label: "Cluster" },
  { id: "genre", label: "Genre", value: (t) => (t.genre ? t.genre.split(", ")[0] : null), categorical: true },
  { id: "era", label: "Release year", value: (t) => t.year ?? null, fmt: (v) => Math.round(v) },
  { id: "discovered", label: "First played", value: (t) => year(t.first_played || t.added), fmt: (v) => Math.floor(v) },
  { id: "last", label: "Last played", value: (t) => year(t.last_played), fmt: (v) => Math.floor(v) },
  { id: "plays", label: "Plays", value: (t) => (t.plays != null ? Math.log1p(t.plays) : null), fmt: (v) => Math.round(Math.expm1(v)).toLocaleString() },
  { id: "skips", label: "Skip rate", value: (t) => (t.skips != null && (t.plays ?? 0) + t.skips >= 3 ? t.skips / ((t.plays ?? 0) + t.skips) : null), fmt: (v) => `${Math.round(v * 100)}%` },
  { id: "tempo", label: "Tempo", value: (t) => t.bpm ?? null, fmt: (v) => `${Math.round(v)} BPM` },
  { id: "energy", label: "Energy", value: (t) => t.energy ?? null, fmt: (v) => v.toFixed(2) },
  { id: "valence", label: "Mood (happy)", value: (t) => t.valence ?? null, fmt: (v) => v.toFixed(2) },
];

function hexToRgb(h) {
  const n = parseInt(h.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
const RAMP_RGB = RAMP.map(hexToRgb);

export function rampColor(f) {
  const x = Math.min(1, Math.max(0, f)) * (RAMP_RGB.length - 1);
  const i = Math.min(RAMP_RGB.length - 2, Math.floor(x));
  const k = x - i;
  const c = RAMP_RGB[i].map((a, j) => Math.round(a + (RAMP_RGB[i + 1][j] - a) * k));
  return `#${c.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}
export const RAMP_CSS = `linear-gradient(90deg, ${RAMP.join(", ")})`;

const pct = (sorted, q) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))))];

/** Lenses this map has data for (a lens needs the value on at least 5% of songs). */
export function availableLenses(tracks) {
  if (!tracks?.length) return [LENSES[0]];
  const sample = tracks.length > 4000 ? tracks.filter((_, i) => i % Math.ceil(tracks.length / 4000) === 0) : tracks;
  return LENSES.filter((l) => !l.value || sample.filter((t) => l.value(t) != null).length >= 0.05 * sample.length);
}

/** { colorOf(track) -> css colour, legend } for one lens. */
export function buildLens(lensId, tracks) {
  const lens = LENSES.find((l) => l.id === lensId) || LENSES[0];
  if (!lens.value) return { lens, colorOf: (t) => colorFor(t.cluster), legend: null };

  if (lens.categorical) {
    // The 8 most common values get the fixed palette in order; the rest share one grey
    const counts = new Map();
    for (const t of tracks) {
      const v = lens.value(t);
      if (v) counts.set(v, (counts.get(v) || 0) + 1);
    }
    const top = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([v]) => v);
    const color = new Map(top.map((v, i) => [v, CLUSTER_COLORS[i]]));
    return {
      lens,
      colorOf: (t) => color.get(lens.value(t)) || MISSING,
      legend: { kind: "swatches", items: [...top.map((v) => ({ label: v, color: color.get(v) })), ...(counts.size > 8 ? [{ label: "Other", color: MISSING }] : [])] },
    };
  }

  // Continuous: stretch the 2nd-98th percentile over the ramp, so one outlier can't flatten it
  const vals = tracks.map(lens.value).filter((v) => v != null && Number.isFinite(v)).sort((a, b) => a - b);
  const lo = vals.length ? pct(vals, 0.02) : 0;
  const hi = vals.length ? pct(vals, 0.98) : 1;
  const span = hi - lo || 1;
  return {
    lens,
    colorOf: (t) => {
      const v = lens.value(t);
      return v == null || !Number.isFinite(v) ? MISSING : rampColor((v - lo) / span);
    },
    legend: { kind: "ramp", lo: lens.fmt(lo), hi: lens.fmt(hi), missing: vals.length < tracks.length },
  };
}
