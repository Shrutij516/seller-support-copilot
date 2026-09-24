import type { NextConfig } from "next";

// Static export: the build emits plain HTML/JS to `out/` for S3 + CloudFront.
// This rules out server features (API routes, SSR, middleware, image optimization).
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
