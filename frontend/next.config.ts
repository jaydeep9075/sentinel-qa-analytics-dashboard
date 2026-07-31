import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ['13.63.14.222'],
  turbopack: {
    root: __dirname,
  },
  // Emits a self-contained .next/standalone server (only the node_modules
  // it actually traced as used, not the full tree) - the Docker runtime
  // stage copies just that instead of the whole node_modules, which is
  // what makes the final image small.
  output: "standalone",
};

export default nextConfig;
