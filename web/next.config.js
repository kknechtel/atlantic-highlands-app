/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // API proxy handled by app/api/[...path]/route.ts
  // Note: `experimental.missingSuspenseWithCSRBailout` was removed in Next 15.
};

module.exports = nextConfig;
