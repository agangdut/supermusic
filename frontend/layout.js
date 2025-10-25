// frontend/app/layout.js
import "./globals.css";
import { Inter } from "next/font/google";

const inter = Inter({ subsets: ["latin"], display: "swap" });

export const metadata = {
  title: "SuperMusic",
  description:
    "Convert audio to MIDI, enrich CSV metadata, and separate stems — all in one workflow.",
  keywords: [
    "SuperMusic",
    "audio to MIDI",
    "stem separation",
    "music analysis",
    "CSV enrichment",
  ],
  authors: [{ name: "SuperMusic" }],
  openGraph: {
    title: "SuperMusic",
    description:
      "Convert audio to MIDI, enrich CSV metadata, and separate stems — all in one workflow.",
    url: "https://supermusic.dev", // update with your actual domain
    siteName: "SuperMusic",
    images: [
      {
        url: "/social-preview.png", // optional social preview
        width: 1200,
        height: 630,
        alt: "SuperMusic Dashboard Preview",
      },
    ],
    locale: "en_US",
    type: "website",
  },
  themeColor: "#0f172a",
  icons: {
    icon: "/favicon.ico", // can also include appleTouchIcon, shortcut, etc.
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className="dark">
      <head />
      <body
        className={`${inter.className} bg-[#0f172a] text-gray-100 antialiased min-h-screen`}
      >
        {/* Global site container */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </div>
      </body>
    </html>
  );
}
