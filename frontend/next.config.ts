import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ['13.63.14.222'],
  turbopack: {
    root: __dirname,
  },
  /* config options here */
};

export default nextConfig;
