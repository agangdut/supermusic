/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    unoptimized: true // if you’re using static images only
  }
};

module.exports = nextConfig;
