// next.config.mjs / next.config.ts
import createMDX from '@next/mdx';
import fs from 'fs';
import type { NextConfig } from 'next';
import path from 'path';

const sharedI18nPath = path.resolve(__dirname, '../i18n');
const localesJsonPath = path.join(sharedI18nPath, 'locales.json');
const sharedLocalesMetadata = fs.existsSync(localesJsonPath)
  ? JSON.parse(fs.readFileSync(localesJsonPath, 'utf-8'))
  : { default: 'en-US', locales: {} };

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
    externalDir: true,
  },

  turbopack: {
    rules: {
      '*.less': {
        loaders: ['less-loader'],
        as: '*.css',
      },
    },
  },

  env: {
    NEXT_PUBLIC_I18N_META: JSON.stringify(sharedLocalesMetadata),
  },

  // 若 pages/ 目录里有 MDX 页面，需要这行；纯 app/ 可删
  pageExtensions: ['ts', 'tsx', 'js', 'jsx', 'md', 'mdx'],
};

export default withMDX(nextConfig);
