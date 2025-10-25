// pages/api/audio/separate.js
import { parseForm, config as base } from "../_uploadUtil";
export const config = base;

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).end();
  try {
    const { files } = await parseForm(req);
    return res.status(200).json({
      ok: true,
      route: "audio/separate",
      receivedFiles: Object.keys(files || {}),
      note: "Stub stem-separation endpoint hit successfully.",
    });
  } catch (e) {
    console.error("[audio/separate] error:", e);
    return res.status(500).json({
      ok: false,
      error: "Upload failed at audio/separate",
      detail: String(e),
    });
  }
}
