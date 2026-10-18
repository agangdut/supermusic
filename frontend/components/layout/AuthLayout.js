import Head from "next/head";

import { Brand, PhoneTabBar } from "@/components/layout/PageShell";

export const authInput = "mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white placeholder:text-gray-600 focus:border-fuchsia-400/60 focus:outline-none";
export const authButton = "w-full rounded-xl bg-gradient-to-r from-fuchsia-600 to-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-fuchsia-600/20 transition hover:brightness-110 disabled:opacity-50";

/** The starry card that sign-in, sign-up and password reset pages sit in. */
export default function AuthLayout({ title, heading, intro, children, below }) {
  return (
    <div className="relative grid min-h-screen place-items-center overflow-hidden bg-[#0b1121] px-4 py-12 text-gray-200 max-md:pb-24">
      <Head><title>{`${title} · SuperMusic`}</title></Head>
      <div aria-hidden className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_#2a1660_0%,_#0b1121_55%)]" />
      <div aria-hidden className="pointer-events-none absolute inset-0 opacity-60"
        style={{ backgroundImage: "radial-gradient(1px 1px at 20% 30%, #fff8, transparent), radial-gradient(1px 1px at 70% 20%, #fff6, transparent), radial-gradient(1.5px 1.5px at 40% 70%, #c084fc, transparent), radial-gradient(1px 1px at 85% 60%, #38bdf8, transparent), radial-gradient(1px 1px at 10% 80%, #f472b6, transparent)" }} />

      <div className="relative w-full max-w-sm">
        <Brand className="mx-auto mb-8 w-fit" />
        <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-6 shadow-2xl backdrop-blur-md">
          <h1 className="text-xl font-bold text-white">{heading}</h1>
          {intro && <p className="mt-1 text-sm text-gray-400">{intro}</p>}
          {children}
        </div>
        {below && <div className="mt-6 text-center text-[11px] leading-5 text-gray-500">{below}</div>}
      </div>
      <PhoneTabBar />
    </div>
  );
}
