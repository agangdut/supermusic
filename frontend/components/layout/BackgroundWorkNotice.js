"use client";

import Link from "next/link";
import { useRouter } from "next/router";
import { useBackgroundWork } from "@/lib/backgroundWork";

// Floating pill shown on every page while something is running
export default function BackgroundWorkNotice() {
  const { jobs = 0, mapImport = 0 } = useBackgroundWork();
  const { pathname } = useRouter();
  if (!jobs && !mapImport) return null;

  const parts = [];
  if (jobs) parts.push({ text: `${jobs} job${jobs > 1 ? "s" : ""} running in Workspace`, href: "/upload" });
  if (mapImport) parts.push({ text: "Music Map import running", href: "/map" });

  return (
    <div
      role="status"
      className="fixed bottom-4 right-4 z-[9000] max-w-sm rounded-xl border border-indigo-400/30
                 bg-[#111a33]/95 px-4 py-3 text-xs text-gray-200 shadow-lg backdrop-blur"
    >
      <div className="flex items-center gap-2 font-semibold text-white">
        <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-400" />
        {parts.map((p, i) => (
          <span key={p.href}>
            {i > 0 && " · "}
            {pathname === p.href ? p.text : <Link href={p.href} className="underline hover:text-indigo-300">{p.text}</Link>}
          </span>
        ))}
      </div>
      <p className="mt-1 text-gray-400 leading-snug">
        It&apos;s safe to switch between Workspace and Music Map. Work keeps running and your results stay where you left them.
        Keep this browser tab open.
      </p>
    </div>
  );
}
