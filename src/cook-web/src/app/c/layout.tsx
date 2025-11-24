'use client';

// Probably don't need this.
// import 'core-js/full';

import './layout.css';
import '@/c-utils/pollyfill';

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
