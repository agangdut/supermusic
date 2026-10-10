// pages/api/midi/transcribe.js
import { parseForm } from "../_uploadUtil";
export const config = { api: { bodyParser: false } };

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).end();
  try {
    const { files } = await parseForm(req);
    return res.status(200).json({
      ok: true,
      route: "midi/transcribe",
      receivedFiles: Object.keys(files || {}),
      note: "Stub transcription endpoint hit successfully.",
    });
  } catch (e) {
    console.error("[midi/transcribe] error:", e);
    return res.status(500).json({
      ok: false,
      error: "Upload failed at midi/transcribe",
      detail: String(e),
    });
  }
}
