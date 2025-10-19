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
  // Support both .md and .mdx
  extension: /\.mdx?$/,
  options: {
    // remarkPlugins: [],
    // rehypePlugins: [],
  },
});

const nextConfig: NextConfig = {
  // Enable standalone output to reduce production image size
  output: 'standalone',

  async redirects() {
    return [{ source: '/', destination: '/main', permanent: true }];
  },

  // Disable image optimization to avoid Sharp dependency
  images: {
    unoptimized: true,
  },

  // Effective only in Turbopack dev
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
  // Include MDX in page extensions if pages/ has MDX pages; for pure app/ it can be removed
  pageExtensions: ['ts', 'tsx', 'js', 'jsx', 'md', 'mdx'],
};

export default withMDX(nextConfig);
