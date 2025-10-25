"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, API_BASE } from "../../utils/fetcher";

function HealthDot({ ok }) {
  const cls = ok == null ? "bg-gray-300" : ok ? "bg-green-500" : "bg-red-500";
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${cls}`} aria-hidden="true" />;
}

/**
 * Props:
 *  - onOpenNav?: () => void
 *  - onOpenLibrary?: () => void
 *  - rightSlot?: ReactNode
 *  - showHealth?: boolean
 *  - title?: string
 */
export default function Navbar({
  onOpenNav,
  onOpenLibrary,
  rightSlot,
  showHealth = true,
  title = "SuperMusic",
}) {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    const check = () => apiFetch("/health").then(() => setHealth(true)).catch(() => setHealth(false));
    check();
    const t = setInterval(check, 15000);
    return () => clearInterval(t);
  }, []);

  return (
    <header className="fixed inset-x-0 top-0 z-50 h-14 bg-white/80 backdrop-blur border-b">
      <div className="mx-auto flex h-full max-w-6xl items-center justify-between px-4">
        <div className="flex items-center gap-3">
          <button
            onClick={onOpenNav}
            className="rounded-lg border px-2.5 py-1.5 text-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            aria-label="Open menu"
          >
            ☰
          </button>
          <Link href="/" className="flex items-center gap-2 font-semibold">
            <img src="/favicon.ico" alt="" className="h-5 w-5" />
            <span>{title}</span>
          </Link>
          <nav className="ml-4 hidden sm:flex items-center gap-3 text-sm">
            <Link href="/" className="hover:underline">Home</Link>
            <Link href="/upload" className="hover:underline">Upload</Link>
          </nav>
          {showHealth && (
            <div className="ml-3 inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs text-gray-700">
              <HealthDot ok={health} />
              <span className="hidden sm:inline">API</span>
              <span className="text-gray-400">|</span>
              <span className="truncate max-w-[140px] text-gray-500">{API_BASE.replace(/^https?:\/\//,"")}</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onOpenLibrary}
            className="rounded-lg border px-3 py-1.5 text-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            📚 Library
          </button>
          {rightSlot}
        </div>
      </div>
    </header>
  );
}
