'use client'

// Probably don't need this.
// import 'core-js/full';

import './layout.css';
import { shifu } from '@/c-service/Shifu';
import '@/c-utils/pollyfill';
import './ShiNiang/index';

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <>
      { children }
    </>
  )
}

if (window['shifuPlugins']) {
  for (const plugin of window['shifuPlugins']) {
    shifu.installPlugin(plugin);
  }
}
