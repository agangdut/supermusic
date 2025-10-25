// frontend/pages/_app.js
import "@/styles/globals.css"; // <-- this pulls in Tailwind (or your CSS)

export default function App({ Component, pageProps }) {
  return <Component {...pageProps} />;
}