// Shared by the page (server-safe) and the 3D view (browser-only).
export const CLUSTER_COLORS = [
  "#a78bfa", "#38bdf8", "#f472b6", "#34d399", "#fbbf24",
  "#fb7185", "#22d3ee", "#c084fc", "#a3e635", "#f97316",
];
export const colorFor = (cluster) => CLUSTER_COLORS[((cluster ?? 0) % CLUSTER_COLORS.length + CLUSTER_COLORS.length) % CLUSTER_COLORS.length];
