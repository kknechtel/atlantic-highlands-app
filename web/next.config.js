/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // Skip static page generation - all pages are dynamic (use client-side data fetching)
  experimental: {
    missingSuspenseWithCSRBailout: false,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
