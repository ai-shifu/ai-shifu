import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      {
        source: '/',
        destination: '/main',
        permanent: true,
      },
    ];
  },

  // Add Turbopack configuration for Less files
  experimental: {
    turbo: {
      rules: {
        '*.less': {
          loaders: ['less-loader'],
          as: '*.css',
        },
      },
    },
  },
};

export default nextConfig;
