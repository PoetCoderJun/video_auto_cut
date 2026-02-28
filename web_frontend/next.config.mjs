import path from "node:path";
import {fileURLToPath} from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  // Allow local dev origins for API <-> frontend and localhost/127.0.0.1 mixed access.
  allowedDevOrigins: [
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
  ],
  turbopack: {
    root: __dirname,
  },
  // Cross-Origin Isolation is required for WebCodecs audio encoding (AAC/MP4) in
  // non-localhost contexts. Without these headers the browser blocks the encoder
  // and throws "No audio codec can be encoded by this browser for container mp4".
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
          { key: "Cross-Origin-Embedder-Policy", value: "require-corp" },
        ],
      },
    ];
  },
};

export default nextConfig;
