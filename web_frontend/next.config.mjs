import path from "node:path";
import {fileURLToPath} from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  allowedDevOrigins: ["http://127.0.0.1:8000", "http://localhost:8000"],
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
