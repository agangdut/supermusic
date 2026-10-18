import { useEffect, useState } from "react";

import { apiFetch } from "@/utils/fetcher";

// Same ids as REASONS in backend/app/core/admin.py
const REASONS = [
  { id: "spam", label: "Spam or advertising" },
  { id: "offensive", label: "Hateful, abusive or sexual" },
  { id: "copyright", label: "Copyright" },
  { id: "personal", label: "Someone's private information" },
  { id: "other", label: "Something else" },
];

const NAMES = { map: "map", profile: "profile", pin: "note", track: "track" };

/**
 * A small "Report" link that opens a box to tell the site's admins something breaks the rules.
 * kind: map | profile | pin | track; target: its id (share id, username, pin id, track id).
 */
export default function ReportButton({ kind, target, className = "", label = "Report" }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [details, setDetails] = useState("");
  const [state, setState] = useState(null); // null | "sending" | "sent" | error message

  useEffect(() => {
    if (!open) return undefined;
    const esc = (e) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [open]);

  const send = async (e) => {
    e.preventDefault();
    setState("sending");
    try {
      await apiFetch("/reports", { method: "POST", body: JSON.stringify({ kind, target: String(target), reason, details: details.trim() || null }) });
      setState("sent");
    } catch (err) {
      setState(err.message || String(err));
    }
  };

  const close = () => { setOpen(false); if (state === "sent") { setReason(""); setDetails(""); setState(null); } };

  return (
    <>
      <button type="button" onClick={(e) => { e.stopPropagation(); e.preventDefault(); setOpen(true); }}
        className={className || "text-xs text-gray-500 hover:text-rose-300"}>
        {label}
      </button>
      {open && (
        <div className="fixed inset-0 z-[90] grid place-items-center bg-black/60 px-4 backdrop-blur-sm" onClick={close} role="dialog" aria-modal="true">
          <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-[#0f1630] p-5 text-left shadow-2xl" onClick={(e) => e.stopPropagation()}>
            {state === "sent" ? (
              <>
                <h2 className="text-base font-semibold text-white">Thanks for telling us</h2>
                <p className="mt-2 text-sm leading-6 text-gray-400">The site&apos;s admins will look at this {NAMES[kind]} and take it down if it breaks the rules.</p>
                <button onClick={close} className="mt-4 rounded-xl bg-white/10 px-4 py-2 text-sm font-semibold text-white hover:bg-white/15">Close</button>
              </>
            ) : (
              <form onSubmit={send}>
                <h2 className="text-base font-semibold text-white">Report this {NAMES[kind]}</h2>
                <p className="mt-1 text-xs text-gray-500">What&apos;s wrong with it?</p>
                <div className="mt-3 space-y-1.5">
                  {REASONS.map((r) => (
                    <label key={r.id} className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm ${reason === r.id ? "border-rose-400/50 bg-rose-500/10 text-white" : "border-white/10 text-gray-300 hover:border-white/20"}`}>
                      <input type="radio" name="reason" value={r.id} checked={reason === r.id} onChange={() => setReason(r.id)} className="accent-rose-400" />
                      {r.label}
                    </label>
                  ))}
                </div>
                <textarea value={details} onChange={(e) => setDetails(e.target.value)} maxLength={1000} rows={2}
                  placeholder="Anything else we should know? (optional)"
                  className="mt-3 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:border-rose-400/50 focus:outline-none" />
                {state && state !== "sending" && <p className="mt-2 text-xs text-rose-300">{state}</p>}
                <div className="mt-3 flex justify-end gap-2">
                  <button type="button" onClick={close} className="rounded-xl px-3 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
                  <button disabled={!reason || state === "sending"}
                    className="rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-500 disabled:opacity-40">
                    {state === "sending" ? "Sending…" : "Send report"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  );
}
