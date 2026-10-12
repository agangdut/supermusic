// frontend/pages/_app.js
import { useRef } from "react";
import "@/styles/globals.css";
import PageTransitionOverlay from "@/components/layout/PageTransitionOverlay";
import BackgroundWorkNotice from "@/components/layout/BackgroundWorkNotice";

// Pages that stay mounted (just hidden) when you switch away, so running jobs,
// uploads and the map you built are still there when you come back
const KEEP_ALIVE = ["/upload", "/map"];

export default function MyApp({ Component, pageProps, router }) {
  const kept = useRef({});
  const path = router.pathname;
  const keep = KEEP_ALIVE.includes(path);
  if (keep && !kept.current[path]) kept.current[path] = <Component {...pageProps} />;

  return (
    <>
      <PageTransitionOverlay />
      {Object.entries(kept.current).map(([p, page]) => (
        <div key={p} hidden={p !== path}>{page}</div>
      ))}
      {!keep && <Component {...pageProps} />}
      <BackgroundWorkNotice />
    </>
  );
}
