"use client";

export default function ToastBanner({ toast }) {
  if (!toast) return null;

  let klass =
    "bg-[#1e253d] text-gray-100 border border-white/10 shadow-[0_10px_30px_rgba(0,0,0,0.8)]";
  if (toast.kind === "ok")
    klass =
      "bg-emerald-600/20 text-emerald-200 border border-emerald-500/40 shadow-[0_10px_30px_rgba(16,185,129,0.3)]";
  if (toast.kind === "err")
    klass =
      "bg-red-600/20 text-red-200 border border-red-500/40 shadow-[0_10px_30px_rgba(239,68,68,0.3)]";
  if (toast.kind === "warn")
    klass =
      "bg-yellow-600/20 text-yellow-200 border border-yellow-500/40 shadow-[0_10px_30px_rgba(234,179,8,0.3)]";

  return (
    <div
      className={`mb-4 rounded-lg px-4 py-2 text-sm font-medium ${klass}`}
    >
      {toast.msg}
    </div>
  );
}
