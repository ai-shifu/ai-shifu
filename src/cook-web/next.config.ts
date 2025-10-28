// next.config.mjs / next.config.ts
import createMDX from '@next/mdx';
import fs from 'fs';
import type { NextConfig } from 'next';
import path from 'path';

// Resolve shared i18n directory robustly for both local and Docker builds
const resolveSharedI18nPath = (): string | null => {
  const candidates = [
    path.resolve(__dirname, 'src/i18n'), // when building from repo root (Docker)
    path.resolve(__dirname, '../i18n'), // when running Next from src/cook-web
    path.resolve(__dirname, '../../i18n'), // monorepo-like layout
    '/app/i18n',
    '/app/src/i18n',
    '/i18n',
  ];
  for (const p of candidates) {
    try {
      if (fs.existsSync(p)) return p;
    } catch {
      // ignore
    }
  }
  return null;
};

const sharedI18nPath = resolveSharedI18nPath();
const sharedLocalesMetadata = (() => {
  if (!sharedI18nPath) return { default: 'en-US', locales: {}, namespaces: [] };
  const localesJsonPath = path.join(sharedI18nPath, 'locales.json');
  try {
    if (fs.existsSync(localesJsonPath)) {
      return JSON.parse(fs.readFileSync(localesJsonPath, 'utf-8'));
    }
  } catch {
    // fall through
  }
  return { default: 'en-US', locales: {}, namespaces: [] };
})();

// Only expose real user-facing locales to the frontend env (hide pseudo-locale)
const allowedFrontendLocales = new Set(['en-US', 'zh-CN']);
const filteredLocales = Object.fromEntries(
  Object.entries(sharedLocalesMetadata.locales || {}).filter(([code]) =>
    allowedFrontendLocales.has(code),
  ),
);
// Filter out any pseudo-locale style namespaces (only allow sane identifiers)
const isValidNs = (s: unknown): s is string =>
  typeof s === 'string' && /^[A-Za-z0-9_.-]+$/.test(s);
const validNamespaces = Array.isArray((sharedLocalesMetadata as any).namespaces)
  ? (sharedLocalesMetadata as any).namespaces.filter(isValidNs)
  : [];

const frontendLocalesMetadata = {
  ...sharedLocalesMetadata,
  locales: filteredLocales,
  namespaces: validNamespaces,
};

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
    NEXT_PUBLIC_I18N_META: JSON.stringify(frontendLocalesMetadata),
  },
  // Include MDX in page extensions if pages/ has MDX pages; for pure app/ it can be removed
  pageExtensions: ['ts', 'tsx', 'js', 'jsx', 'md', 'mdx'],
};

export default withMDX(nextConfig);
