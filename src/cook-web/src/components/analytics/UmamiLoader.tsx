'use client';

import { useEffect } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { useEnvStore } from '@/c-store';
import { useShallow } from 'zustand/react/shallow';
import { flushUmamiPageviews, trackPageview } from '@/c-common/tools/tracking';

const SCRIPT_ID = 'umami-analytics-script';

const ensureUmamiScript = (src: string, websiteId: string) => {
  const existing = document.getElementById(SCRIPT_ID);
  if (existing) {
    existing.setAttribute('data-website-id', websiteId);
    flushUmamiPageviews();
    return;
  }

  const script = document.createElement('script');
  script.id = SCRIPT_ID;
  script.defer = true;
  script.src = src;
  script.setAttribute('data-website-id', websiteId);
  script.setAttribute('data-auto-track', 'false');
  script.addEventListener('load', () => {
    flushUmamiPageviews();
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
  const searchParams = useSearchParams();
  const search = searchParams?.toString();
  useEffect(() => {
    if (!umamiScriptSrc || !umamiWebsiteId) {
      return;
    }
    ensureUmamiScript(umamiScriptSrc, umamiWebsiteId);
  }, [umamiScriptSrc, umamiWebsiteId]);

  useEffect(() => {
    trackPageview();
  }, [pathname, search]);

  return null;
};

export default UmamiLoader;
