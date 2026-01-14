'use client';

// Probably don't need this.
// import 'core-js/full';

import './layout.css';
import '@/c-utils/pollyfill';
import { useViewportHeight } from '@/hooks/useViewportHeight';

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  useViewportHeight();

  return <>{children}</>;
}
