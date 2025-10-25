// frontend/pages/api/jobs/[id].js

export default async function handler(req, res) {
  const {
    query: { id },
    method,
  } = req;

  if (method !== "GET") return res.status(405).end();

  // In the future, you'd ask your backend for job status by ID.
  // For now we'll just pretend everything finishes instantly.
  return res.status(200).json({
    id,
    status: "done",
    message: "Job finished (stub).",
    result: {
      summary: "This is placeholder job data from /api/jobs/[id].js",
    },
  });
}
