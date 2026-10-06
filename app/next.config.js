/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: { unoptimized: true },
  // The precomputed data in public/data is served as static files, so the app
  // runs with no backend (Vercel-only, or a laptop with no network).
  async headers() {
    return [
      {
        source: "/data/:path*",
        headers: [{ key: "Cache-Control", value: "public, max-age=3600" }],
      },
    ];
  },
};

module.exports = nextConfig;
