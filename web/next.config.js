/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // Skip static page generation - all pages are dynamic (use client-side data fetching)
  experimental: {
    missingSuspenseWithCSRBailout: false,
  },
  // API proxy handled by app/api/[...path]/route.ts
};

module.exports = nextConfig;
