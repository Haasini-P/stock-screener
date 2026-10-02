import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The frontend Dockerfile copies .next/standalone — without this, that
  // directory is never produced and the Docker build fails at COPY.
  output: "standalone",
};

export default nextConfig;
