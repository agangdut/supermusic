// frontend/pages/_app.js
import { useEffect, useRef } from "react";
import Head from "next/head";
import "@/styles/globals.css";
import PageTransitionOverlay from "@/components/layout/PageTransitionOverlay";
import BackgroundWorkNotice from "@/components/layout/BackgroundWorkNotice";
import { countPageView } from "@/utils/pageViews";

// Pages that stay mounted (just hidden) when you switch away, so running jobs,
// uploads and the map you built are still there when you come back
const KEEP_ALIVE = ["/upload", "/"];

export default function MyApp({ Component, pageProps, router }) {
  const kept = useRef({});
  const path = router.pathname;
  const keep = KEEP_ALIVE.includes(path);
  if (keep && !kept.current[path]) kept.current[path] = <Component {...pageProps} />;

  // Visitor stats for the admin page: the page's route only (e.g. /u/[username]), no cookies
  useEffect(() => { if (router.isReady) countPageView(path); }, [path, router.isReady]);

  return (
    <>
      <Head>
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
      </Head>
      <PageTransitionOverlay />
      {Object.entries(kept.current).map(([p, page]) => (
        <div key={p} hidden={p !== path}>{page}</div>
      ))}
      {!keep && <Component {...pageProps} />}
      <BackgroundWorkNotice />
    </>
  );
}
