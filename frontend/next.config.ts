import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async headers() {
    return [
      {
        // Chat-background videos/posters: cached forever by the browser so repeat visits
        // (and reopening the popup) never re-download them. Consequence: replacing an
        // asset requires a new filename — never overwrite an existing file in place.
        source: "/:prefix(videos|images)/:path*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
        ],
      },
    ];
  },
};

export default nextConfig;
