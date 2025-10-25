// frontend/pages/_app.js
import "@/styles/globals.css";
import PageTransitionOverlay from "@/components/layout/PageTransitionOverlay";

export default function MyApp({ Component, pageProps }) {
  return (
    <>
      <PageTransitionOverlay />
      <Component {...pageProps} />
    </>
  );
}
