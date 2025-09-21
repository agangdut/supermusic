import { parseForm, config as base } from "./_uploadUtil";
export const config = base;

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).end();
  try {
    const { files } = await parseForm(req);
    // TODO: call Python service to enrich metadata using the CSV
    return res.status(200).json({ ok: true, received: files });
  } catch (e) {
    console.error(e);
    return res.status(500).send("Upload failed");
  }
}
