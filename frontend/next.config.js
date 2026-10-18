/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Docker: copy only the files the server needs into .next/standalone, so the
  // image doesn't carry all of node_modules (see Dockerfile)
  output: "standalone",
  // GitHub Pages demo build (see .github/workflows/pages.yml): a static export under /supermusic
  ...(process.env.NEXT_PUBLIC_DEMO
    ? { output: "export", basePath: process.env.NEXT_PUBLIC_BASE_PATH || "", trailingSlash: true }
    : {}),
  images: {
    unoptimized: true // if you’re using static images only
  }
};

module.exports = nextConfig;
