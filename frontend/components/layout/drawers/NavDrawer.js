"use client";
import Link from "next/link";
import { useRouter } from "next/router";
import SlideOver from "../overlays/SlideOver";

/**
 * Props:
 *  - open: boolean
 *  - onClose: () => void
 *  - items?: Array<{ href: string, label: string, icon?: string }>
 */
export default function NavDrawer({
  open,
  onClose,
  items = [
    { href: "/upload", label: "Upload", icon: "⤴️" },
    { href: "/", label: "Home", icon: "🏠" },
  ],
}) {
  const { pathname } = useRouter();

  return (
    <SlideOver open={open} onClose={onClose} side="left" title="Menu">
      <nav className="space-y-1">
        {items.map((it) => {
          const active = pathname === it.href;
          return (
            <Link
              key={it.href}
              href={it.href}
              onClick={onClose}
              className={[
                "flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition",
                active
                  ? "bg-blue-50 text-blue-700 border border-blue-200"
                  : "text-gray-700 hover:bg-gray-50",
              ].join(" ")}
            >
              <span className="w-5 text-center">{it.icon || "•"}</span>
              <span className="truncate">{it.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="mt-6">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
          Quick links
        </h3>
        <ul className="mt-2 space-y-1 text-sm">
          <li>
            <a
              href="/architecture-diagram.png"
              target="_blank"
              rel="noreferrer"
              className="block rounded-lg px-3 py-2 text-gray-700 hover:bg-gray-50"
            >
              🧩 Architecture Diagram
            </a>
          </li>
          <li>
            <a
              href="/favicon.ico"
              target="_blank"
              rel="noreferrer"
              className="block rounded-lg px-3 py-2 text-gray-700 hover:bg-gray-50"
            >
              🖼️ Favicon
            </a>
          </li>
        </ul>
      </div>
    </SlideOver>
  );
}
