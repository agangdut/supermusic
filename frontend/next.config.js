/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // GitHub Pages demo build (see .github/workflows/pages.yml): a static export under /supermusic
  ...(process.env.NEXT_PUBLIC_DEMO
    ? { output: "export", basePath: process.env.NEXT_PUBLIC_BASE_PATH || "", trailingSlash: true }
    : {}),
  images: {
    unoptimized: true // if you’re using static images only
  }
};

module.exports = nextConfig;
