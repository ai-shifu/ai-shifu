'use client';

import { useEffect, useSyncExternalStore } from 'react';
import { usePathname } from 'next/navigation';
import { useEnvStore } from '@/store';
import { useShallow } from 'zustand/react/shallow';
import {
  flushUmamiIdentify,
  getTrackingResumeGeneration,
  subscribeToTrackingResume,
  trackPageview,
} from '@/lib/tracking';
import { useUserStore } from '@/store';

const SCRIPT_ID = 'umami-analytics-script';
const AUTO_TRACK_ATTRIBUTE_VALUE = 'false';

const ensureUmamiScript = (src: string, websiteId: string) => {
  const existing = document.getElementById(SCRIPT_ID);
  if (existing) {
    existing.setAttribute('data-website-id', websiteId);
    existing.setAttribute('data-auto-track', AUTO_TRACK_ATTRIBUTE_VALUE);
    existing.removeAttribute('data-auto-pageview');
    flushUmamiIdentify();
    return;
  }

  const script = document.createElement('script');
  script.id = SCRIPT_ID;
  script.defer = true;
  script.src = src;
  script.setAttribute('data-website-id', websiteId);
  script.setAttribute('data-auto-track', AUTO_TRACK_ATTRIBUTE_VALUE);
  script.addEventListener('load', () => {
    flushUmamiIdentify();
  });
  document.head.appendChild(script);
};

export const UmamiLoader = () => {
  const { umamiScriptSrc, umamiWebsiteId } = useEnvStore(
    useShallow(state => ({
      umamiScriptSrc: state.umamiScriptSrc,
      umamiWebsiteId: state.umamiWebsiteId,
    })),
  );
  const pathname = usePathname();
  const isUserInitialized = useUserStore(state => state.isInitialized);
  const trackingResumeGeneration = useSyncExternalStore(
    subscribeToTrackingResume,
    getTrackingResumeGeneration,
    () => 0,
  );

  useEffect(() => {
    if (!umamiScriptSrc || !umamiWebsiteId) {
      return;
    }
    ensureUmamiScript(umamiScriptSrc, umamiWebsiteId);
  }, [umamiScriptSrc, umamiWebsiteId]);

  useEffect(() => {
    if (!umamiScriptSrc || !umamiWebsiteId) {
      return;
    }

    if (!isUserInitialized) {
      return;
    }

    trackPageview(pathname);
  }, [
    pathname,
    umamiScriptSrc,
    umamiWebsiteId,
    isUserInitialized,
    trackingResumeGeneration,
  ]);

  return null;
};

export default UmamiLoader;
