'use client';

// Probably don't need this.
// import 'core-js/full';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';

import { useEnvStore } from '@/c-store/envStore';
import { environment } from '@/config/environment';
import { redirectToHomeUrlIfRootPath } from '@/lib/utils';

import './layout.css';
import '@/c-utils/pollyfill';

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const homeUrl = useEnvStore(state => state.homeUrl);
  const runtimeConfigLoaded = useEnvStore(state => state.runtimeConfigLoaded);
  const isCourseEntryPath = pathname?.replace(/\/+$/, '') === '/c';

  useEffect(() => {
    if (!runtimeConfigLoaded || !isCourseEntryPath) {
      return;
    }
    redirectToHomeUrlIfRootPath(homeUrl || environment.homeUrl);
  }, [homeUrl, isCourseEntryPath, runtimeConfigLoaded]);

  if (isCourseEntryPath) {
    return null;
  }

  return <>{children}</>;
}
