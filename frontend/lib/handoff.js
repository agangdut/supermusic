// Files carried from one page to another without uploading them twice
// (the map hands an un-enriched CSV to the Studio).
let pendingCsv = null;

export function handCsvToStudio(files) {
  pendingCsv = files;
}

export function takeCsvForStudio() {
  const files = pendingCsv;
  pendingCsv = null;
  return files;
}

// Which details a library CSV is missing, from its header line. Listening histories
// (JSON) never have them, so only CSVs are checked. Returns [] when it looks enriched.
const DETAILS = [
  ["genre", /^(genres?|style|tags)$/],
  ["tempo", /^(bpm|tempo)$/],
  ["key", /^(key|musical_key|camelot|key_name)$/],
  ["energy", /^(energy|valence|danceability)$/],
];

export async function missingDetails(files) {
  const csvs = files.filter((f) => /\.(csv|tsv)$/i.test(f.name));
  if (!csvs.length) return [];
  const found = new Set();
  for (const f of csvs) {
    const head = (await f.slice(0, 8192).text()).split(/\r?\n/)[0] || "";
    head.split(/[,\t;]/)
      .map((c) => c.replace(/^"|"$/g, "").trim().toLowerCase().replace(/\s*\(.*\)$/, "").replace(/\s+/g, "_"))
      .forEach((c) => DETAILS.forEach(([name, re]) => { if (re.test(c)) found.add(name); }));
  }
  return DETAILS.map(([name]) => name).filter((n) => !found.has(n));
}
