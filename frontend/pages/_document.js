import { Html, Head, Main, NextScript } from "next/document";

export default function Document() {
  return (
    <Html lang="en">
      <Head>
        {/* Installable from the browser menu ("Add to Home Screen") on phones and desktops */}
        <link rel="manifest" href={`${process.env.NEXT_PUBLIC_BASE_PATH || ""}/manifest.webmanifest`} />
        <meta name="theme-color" content="#0b1121" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <link rel="apple-touch-icon" href={`${process.env.NEXT_PUBLIC_BASE_PATH || ""}/apple-touch-icon.png`} />
        <link rel="icon" href={`${process.env.NEXT_PUBLIC_BASE_PATH || ""}/favicon.ico`} />
      </Head>
      <body className="bg-[#0b1121]">
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
