'use client';

import { useEffect } from 'react';
import { useEnvStore } from '@/c-store';
import { useShallow } from 'zustand/react/shallow';

const SCRIPT_ID = 'umami-analytics-script';

const ensureUmamiScript = (src: string, websiteId: string) => {
  const existing = document.getElementById(SCRIPT_ID);
  if (existing) {
    existing.setAttribute('data-website-id', websiteId);
    return;
  }

  const script = document.createElement('script');
  script.id = SCRIPT_ID;
  script.defer = true;
  script.src = src;
  script.setAttribute('data-website-id', websiteId);
  script.setAttribute('data-auto-track', 'true');
  document.head.appendChild(script);
};

export const UmamiLoader = () => {
  const { umamiScriptSrc, umamiWebsiteId } = useEnvStore(
    useShallow(state => ({
      umamiScriptSrc: state.umamiScriptSrc,
      umamiWebsiteId: state.umamiWebsiteId,
    })),
  );

  useEffect(() => {
    if (!umamiScriptSrc || !umamiWebsiteId) {
      return;
    }
    ensureUmamiScript(umamiScriptSrc, umamiWebsiteId);
  }, [umamiScriptSrc, umamiWebsiteId]);

  return null;
};

export default UmamiLoader;
