import { Metadata, Viewport } from 'next';

export const metadata: Metadata = {
  title: 'AI-Shifu',
  description: '',
  // Suppress browser auto-translation. Edge/Chrome translate rewrites React-managed
  // text nodes (wrapping them in <font>), which breaks the reconciler's
  // removeChild/insertBefore and crashes the lesson preview. See DomReconcilerGuard.
  other: { google: 'notranslate' },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
};
