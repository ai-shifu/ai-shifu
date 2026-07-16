'use client';

// Probably don't need this.
// import 'core-js/full';

import { useEffect } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';

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
  const searchParams = useSearchParams();
  const homeUrl = useEnvStore(state => state.homeUrl);
  const runtimeConfigLoaded = useEnvStore(state => state.runtimeConfigLoaded);
  const explicitCourseId = searchParams?.get('courseId')?.trim() ?? '';
  const isBareCourseEntryPath =
    pathname?.replace(/\/+$/, '') === '/c' && !explicitCourseId;

  useEffect(() => {
    if (!runtimeConfigLoaded || !isBareCourseEntryPath) {
      return;
    }
    const redirected = redirectToHomeUrlIfRootPath(
      homeUrl || environment.homeUrl,
    );
    if (!redirected) {
      window.location.replace('/404');
    }
  }, [homeUrl, isBareCourseEntryPath, runtimeConfigLoaded]);

  if (isBareCourseEntryPath) {
    return null;
  }

  return <>{children}</>;
}
