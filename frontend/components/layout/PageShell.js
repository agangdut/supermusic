"use client";

import React from "react";
import Link from "next/link";
// import Navbar from "./Navbar"; // optional future nav

/**
 * PageShell wraps all pages in the global SuperMusic chrome.
 *
 * - Dark background across the whole viewport
 * - Light text
 * - Sticky-ish header with brand
 * - Centers main page content in a max-width container
 */
export default function PageShell({ children }) {
  return (
    <div className="min-h-screen w-full bg-[#0b1121] text-gray-200 flex flex-col">
      {/* Top header / brand */}
      <header className="px-4 py-4 lg:px-8 flex items-center justify-between border-b border-white/10 bg-[#0b1121]">
        {/* Brand / home link */}
        <Link
          href="/"
          className="flex items-center gap-2 group"
        >
          <span className="text-sm font-semibold tracking-tight flex items-baseline">
            <span className="text-gray-100 group-hover:text-white transition-colors">
              Super
            </span>
            <span
              className="ml-1 bg-gradient-to-r from-purple-400 to-indigo-400 bg-clip-text text-transparent
                         drop-shadow-[0_0_8px_rgba(168,85,247,0.6)]
                         group-hover:drop-shadow-[0_0_10px_rgba(168,85,247,0.9)]
                         transition-all"
            >
              Music
            </span>
          </span>
        </Link>

        {/* Right side placeholder (account menu / nav actions later) */}
        <div className="text-[11px] text-gray-500">
          {/* e.g. <Navbar /> / profile menu / etc later */}
        </div>
      </header>

      {/* Main page area */}
      <main className="flex-1 px-4 pb-16 lg:px-8 flex justify-center">
        <div className="w-full max-w-[1500px] pt-6 lg:pt-10">{children}</div>
      </main>
    </div>
  );
}

