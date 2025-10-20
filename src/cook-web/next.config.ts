// next.config.mjs / next.config.ts
import createMDX from '@next/mdx';
import type { NextConfig } from 'next';

const withMDX = createMDX({
  extension: /\.mdx?$/, // 同时支持 .md / .mdx，按需改
  options: {
    // remarkPlugins: [],
    // rehypePlugins: [],
  },
});

const nextConfig: NextConfig = {
  // 启用 standalone 输出模式,大幅减小生产镜像体积
  output: 'standalone',

  async redirects() {
    return [{ source: '/', destination: '/main', permanent: true }];
  },

  // Disable image optimization to avoid Sharp dependency
  images: {
    unoptimized: true,
  },

  // 仅 Turbopack dev 时生效
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
  // 若 pages/ 目录里有 MDX 页面，需要这行；纯 app/ 可删
  pageExtensions: ['ts', 'tsx', 'js', 'jsx', 'md', 'mdx'],
};

export default withMDX(nextConfig);
