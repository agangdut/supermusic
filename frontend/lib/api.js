// frontend/lib/api.js
// lib/api.js
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export async function getJobFiles(kind, jobId) {
  const res = await fetch(`${API_BASE}/jobs/${encodeURIComponent(kind)}/${encodeURIComponent(jobId)}`);
  if (!res.ok) return { ok: false, files: [], status: "unknown" };
  return res.json(); // { ok, files, status, progress }
}

// Generic polling helper
export async function pollJobFiles(kind, jobId, { tries = 30, intervalMs = 2000 } = {}) {
  for (let i = 0; i < tries; i++) {
    const data = await getJobFiles(kind, jobId);
    if (data.ok && Array.isArray(data.files) && data.files.length) return data.files;
    await new Promise(r => setTimeout(r, intervalMs));
  }
  throw new Error("Polling timed out.");
}
