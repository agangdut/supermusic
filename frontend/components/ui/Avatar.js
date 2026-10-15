// A round badge with someone's initials, coloured by their username (no photo uploads yet)
const HUES = [
  ["#a855f7", "#6366f1"], ["#ec4899", "#a855f7"], ["#38bdf8", "#6366f1"], ["#34d399", "#0ea5e9"],
  ["#f59e0b", "#ec4899"], ["#f472b6", "#fb7185"], ["#22d3ee", "#a78bfa"], ["#c084fc", "#f0abfc"],
];

function hash(s) {
  let h = 0;
  for (const ch of String(s || "")) h = (h * 31 + ch.charCodeAt(0)) | 0;
  return Math.abs(h);
}

export default function Avatar({ name, username, size = 32, className = "" }) {
  const label = (name || username || "?").trim();
  const initials = label.split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase()).join("") || "?";
  const [a, b] = HUES[hash(username || name) % HUES.length];
  return (
    <span
      aria-hidden="true"
      className={`inline-grid shrink-0 place-items-center rounded-full font-semibold text-white ring-1 ring-white/15 ${className}`}
      style={{ width: size, height: size, fontSize: size * 0.38, background: `linear-gradient(135deg, ${a}, ${b})` }}
    >
      {initials}
    </span>
  );
}
