"use client";

import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useRef, useState } from "react";

import Avatar from "@/components/ui/Avatar";
import { refreshMe, signOut, useAuth } from "@/lib/auth";

// Top navigation on desktop; on phones the main places move to a tab bar at the bottom
const NAV = [
  { href: "/", label: "Map", icon: "map" },
  { href: "/maps", label: "Explore", icon: "explore" },
  { href: "/atlas", label: "Atlas", icon: "atlas" },
  { href: "/feed", label: "Feed", icon: "feed", signedIn: true },
  { href: "/play", label: "Play", icon: "play" },
  { href: "/artists", label: "Artists", icon: "artists" },
  { href: "/upload", label: "Studio", icon: "studio" },
];

// Simple line icons, so every platform draws the tab bar the same way
const ICON_PATHS = {
  map: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z M18.5 16.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z",
  explore: "M12 21a9 9 0 100-18 9 9 0 000 18z M15.5 8.5l-2 5-5 2 2-5z",
  atlas: "M12 15a3 3 0 100-6 3 3 0 000 6z M3 12c0-2 4-4.5 9-4.5s9 2.5 9 4.5-4 4.5-9 4.5S3 14 3 12z",
  feed: "M4 6h16 M4 12h16 M4 18h10",
  play: "M6 4h12a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2z M9 9h.01 M15 15h.01 M15 9h.01 M9 15h.01",
  artists: "M12 3a3 3 0 013 3v5a3 3 0 01-6 0V6a3 3 0 013-3z M6 11a6 6 0 0012 0 M12 17v4",
  studio: "M5 4v16 M12 4v16 M19 4v16 M3 9h4 M10 15h4 M17 7h4",
  you: "M12 12a4 4 0 100-8 4 4 0 000 8z M4 21a8 8 0 0116 0",
};

export function NavIcon({ name, className = "h-5 w-5" }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d={ICON_PATHS[name]} />
    </svg>
  );
}
const PHONE_TABS = ["/", "/maps", "/atlas", "/play"];

const active = (pathname, href) => (href === "/" ? pathname === "/" || pathname === "/map" : pathname.startsWith(href));

export function Brand({ className = "" }) {
  return (
    <Link href="/" className={`group flex items-center gap-2 ${className}`}>
      <span className="relative grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-fuchsia-500 to-indigo-600 shadow-[0_0_18px_rgba(168,85,247,0.55)]">
        <span className="h-2 w-2 rounded-full bg-white shadow-[0_0_8px_white]" />
      </span>
      <span className="text-[15px] font-semibold tracking-tight">
        <span className="text-gray-100 group-hover:text-white">Super</span>
        <span className="bg-gradient-to-r from-purple-400 to-indigo-400 bg-clip-text text-transparent">Music</span>
      </span>
    </Link>
  );
}

function UserMenu() {
  const { user, ready } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef();
  const router = useRouter();
  useEffect(() => { refreshMe(); }, []);
  useEffect(() => {
    const close = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, []);
  if (!ready) return <span className="h-8 w-8" />;
  if (!user) {
    return (
      <Link
        href={`/login?next=${encodeURIComponent(router.asPath)}`}
        className="rounded-lg bg-white/10 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-white/15"
      >
        Sign in
      </Link>
    );
  }
  const item = "block w-full rounded-lg px-3 py-2 text-left text-sm text-gray-300 hover:bg-white/5 hover:text-white";
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} aria-label="Your account" aria-expanded={open}
        className="flex items-center gap-2 rounded-full p-0.5 transition hover:ring-2 hover:ring-fuchsia-400/40">
        <Avatar name={user.display_name} username={user.username} size={32} />
      </button>
      {open && (
        <div className="absolute right-0 top-11 z-[60] w-56 rounded-xl border border-white/10 bg-[#0f1630]/95 p-1.5 shadow-2xl backdrop-blur">
          <div className="px-3 py-2">
            <div className="truncate text-sm font-semibold text-white">{user.display_name}</div>
            <div className="truncate text-xs text-gray-500">@{user.username}</div>
          </div>
          <div className="my-1 h-px bg-white/10" />
          <Link href={`/u/${user.username}`} className={item} onClick={() => setOpen(false)}>Your profile</Link>
          <Link href="/feed" className={item} onClick={() => setOpen(false)}>Feed &amp; weekly digest</Link>
          <Link href="/artists" className={item} onClick={() => setOpen(false)}>Your tracks</Link>
          <div className="my-1 h-px bg-white/10" />
          <button className={item} onClick={() => { signOut(); setOpen(false); }}>Sign out</button>
        </div>
      )}
    </div>
  );
}

/**
 * The app's frame: top bar, and on phones a bottom tab bar.
 * bleed: the page fills the whole width with no padding (the map home page).
 */
export default function PageShell({ children, bleed = false }) {
  const { pathname } = useRouter();
  const { user } = useAuth();
  const [menu, setMenu] = useState(false);
  useEffect(() => { setMenu(false); }, [pathname]);
  const nav = NAV.filter((n) => !n.signedIn || user);

  return (
    <div className="flex min-h-screen w-full flex-col bg-[#0b1121] text-gray-200">
      <header className="sticky top-0 z-50 border-b border-white/10 bg-[#0b1121]/85 backdrop-blur-md">
        <div className="flex h-14 items-center gap-4 px-4 lg:px-6">
          <Brand />
          <nav className="ml-4 hidden items-center gap-0.5 md:flex">
            {nav.map((l) => (
              <Link key={l.href} href={l.href}
                className={`rounded-lg px-3 py-1.5 text-[13px] font-medium transition ${
                  active(pathname, l.href) ? "bg-white/10 text-white" : "text-gray-400 hover:bg-white/5 hover:text-white"
                }`}>
                {l.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <button onClick={() => setMenu((m) => !m)} aria-label="More pages"
              className="rounded-lg px-2.5 py-1.5 text-sm text-gray-300 hover:bg-white/5 md:hidden">⋯</button>
            <UserMenu />
          </div>
        </div>
        {menu && (
          <nav className="grid grid-cols-2 gap-1 border-t border-white/10 p-2 md:hidden">
            {nav.map((l) => (
              <Link key={l.href} href={l.href}
                className={`flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm ${active(pathname, l.href) ? "bg-white/10 text-white" : "text-gray-300"}`}>
                <NavIcon name={l.icon} className="h-4 w-4 text-gray-400" />{l.label}
              </Link>
            ))}
          </nav>
        )}
      </header>

      <main className={bleed ? "flex-1 pb-16 md:pb-0" : "flex flex-1 justify-center px-4 pb-24 md:pb-16 lg:px-8"}>
        {bleed ? children : <div className="w-full max-w-[1400px] pt-6 lg:pt-10">{children}</div>}
      </main>

      {/* Phone tab bar */}
      <nav className="fixed inset-x-0 bottom-0 z-50 grid grid-cols-5 border-t border-white/10 bg-[#0b1121]/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
        {[...NAV.filter((n) => PHONE_TABS.includes(n.href)),
          user ? { href: `/u/${user.username}`, label: "You", icon: "you" } : { href: "/login", label: "Sign in", icon: "you" }].map((l) => (
          <Link key={l.href} href={l.href}
            className={`flex flex-col items-center gap-0.5 py-2 text-[10px] ${active(pathname, l.href) ? "text-white" : "text-gray-500"}`}>
            <NavIcon name={l.icon} className={`h-5 w-5 ${active(pathname, l.href) ? "text-fuchsia-300" : ""}`} />
            {l.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
