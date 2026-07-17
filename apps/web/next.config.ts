import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // Keep production and development artifacts separate. Running Playwright
  // after `next build` must not reuse an incompatible client manifest.
  distDir: process.env.NODE_ENV === "development" ? ".next-dev" : ".next",
  turbopack: {
    root: path.resolve(__dirname, "../.."),
  },
};

export default nextConfig;
