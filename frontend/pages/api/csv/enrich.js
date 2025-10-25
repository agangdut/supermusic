// pages/api/csv/enrich.js
import { parseForm, config as base } from "../_uploadUtil";
export const config = base;

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).end();
  try {
    const { files } = await parseForm(req);
    return res.status(200).json({
      ok: true,
      route: "csv/enrich",
      receivedFiles: Object.keys(files || {}),
      note: "Stub CSV enrichment endpoint hit successfully.",
    });
  } catch (e) {
    console.error("[csv/enrich] error:", e);
    return res.status(500).json({
      ok: false,
      error: "Upload failed at csv/enrich",
      detail: String(e),
    });
  }
}
