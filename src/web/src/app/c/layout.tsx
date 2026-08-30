'use client';

// Probably don't need this.
// import 'core-js/full';

import { useEffect } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

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
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const homeUrl = useEnvStore(state => state.homeUrl);
  const runtimeConfigLoaded = useEnvStore(state => state.runtimeConfigLoaded);
  const normalizedPath = pathname?.replace(/\/+$/, '');
  const serializedSearchParams = searchParams?.toString() ?? '';
  const explicitCourseId = searchParams?.get('courseId')?.trim() ?? '';
  const isCourseEntryPath = normalizedPath === '/c';
  const isCourseQueryEntryPath = isCourseEntryPath && !!explicitCourseId;
  const isBareCourseEntryPath = isCourseEntryPath && !explicitCourseId;

  useEffect(() => {
    if (!isCourseQueryEntryPath) {
      return;
    }
    const remainingSearchParams = new URLSearchParams(serializedSearchParams);
    remainingSearchParams.delete('courseId');
    const remainingQuery = remainingSearchParams.toString();
    const hash = window.location.hash;
    router.replace(
      `/c/${encodeURIComponent(explicitCourseId)}` +
        `${remainingQuery ? `?${remainingQuery}` : ''}${hash}`,
    );
  }, [
    explicitCourseId,
    isCourseQueryEntryPath,
    router,
    serializedSearchParams,
  ]);

  useEffect(() => {
    if (!runtimeConfigLoaded || !isBareCourseEntryPath) {
      return;
    }
    const redirected = redirectToHomeUrlIfRootPath(
      homeUrl || environment.homeUrl,
    );
    if (!redirected) {
      router.replace('/404');
    }
  }, [homeUrl, isBareCourseEntryPath, router, runtimeConfigLoaded]);

  if (isCourseEntryPath) {
    return null;
  }

  return <>{children}</>;
}
