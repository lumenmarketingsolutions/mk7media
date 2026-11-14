import type { NextConfig } from "next";

/* Static export: the site is served as plain HTML by the mk7media Flask service. */
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
