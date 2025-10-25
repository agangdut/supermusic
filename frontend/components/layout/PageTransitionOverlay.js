"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/router";

export default function PageTransitionOverlay() {
  const router = useRouter();
  const [isTransitioning, setIsTransitioning] = useState(false);

  useEffect(() => {
    const handleStart = () => setIsTransitioning(true);
    const handleDone = () => setIsTransitioning(false);

    router.events.on("routeChangeStart", handleStart);
    router.events.on("routeChangeComplete", handleDone);
    router.events.on("routeChangeError", handleDone);

    return () => {
      router.events.off("routeChangeStart", handleStart);
      router.events.off("routeChangeComplete", handleDone);
      router.events.off("routeChangeError", handleDone);
    };
  }, [router.events]);

  if (!isTransitioning) return null;

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center
                 bg-[#0f172a] text-gray-300 text-xs tracking-wide"
    >
      <div className="flex flex-col items-center gap-2">
        <div
          className="w-4 h-4 rounded-full bg-gradient-to-r from-purple-500 to-indigo-500
                     shadow-[0_0_20px_rgba(168,85,247,0.8)]
                     animate-pulse"
        />
        <div className="text-[11px] text-gray-400">Loading…</div>
      </div>
    </div>
  );
}
