import Head from "next/head";

import PageShell from "@/components/layout/PageShell";

// Where people can reach whoever runs this site (set CONTACT_EMAIL when deploying)
export const CONTACT = process.env.NEXT_PUBLIC_CONTACT_EMAIL || "";

export function Contact() {
  return CONTACT
    ? <a href={`mailto:${CONTACT}`} className="text-fuchsia-300 underline">{CONTACT}</a>
    : <a href="https://github.com/agangdut/supermusic/issues" className="text-fuchsia-300 underline">the project&apos;s issue page</a>;
}

export default function LegalPage({ title, updated, children }) {
  return (
    <PageShell>
      <Head><title>{`${title} · SuperMusic`}</title></Head>
      <article className="mx-auto max-w-2xl text-sm leading-7 text-gray-300 [&_h2]:mt-8 [&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-white [&_li]:ml-5 [&_li]:list-disc [&_p]:mt-3 [&_ul]:mt-3">
        <h1 className="text-2xl font-bold tracking-tight text-white">{title}</h1>
        <p className="text-xs text-gray-500">Last updated {updated}</p>
        {children}
      </article>
    </PageShell>
  );
}
