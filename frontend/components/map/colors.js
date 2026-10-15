// Shared by the page (server-safe) and the 3D view (browser-only).
export const CLUSTER_COLORS = [
  "#a78bfa", "#38bdf8", "#f472b6", "#34d399", "#fbbf24",
  "#fb7185", "#22d3ee", "#c084fc", "#a3e635", "#f97316",
];
// Each cluster's galaxy name ("Andromeda"); maps saved before names existed fall back to the genre
export const clusterName = (c) => c?.name || c?.label?.split(" · ")[0] || "Cluster";
// What's in it ("Neo-Soul · A minor"), shown under the galaxy name
export const clusterGenre = (c) => c?.label || "";

export const colorFor = (cluster) => CLUSTER_COLORS[((cluster ?? 0) % CLUSTER_COLORS.length + CLUSTER_COLORS.length) % CLUSTER_COLORS.length];
