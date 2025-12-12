'use client';

import { useEffect } from 'react';
import { initializeEnvData } from '@/lib/initializeEnvData';
import { useEnvStore } from '@/c-store';

const RuntimeConfigInitializer = () => {
  const faviconUrl = useEnvStore(state => state.faviconUrl);
  useEffect(() => {
    initializeEnvData();
  }, []);

  useEffect(() => {
    if (!faviconUrl) return;
    const href = `${faviconUrl}${faviconUrl.includes('?') ? '&' : '?'}v=${Date.now()}`;

    const selectors = [
      "link[rel='icon']",
      "link[rel='shortcut icon']",
      "link[rel='apple-touch-icon']",
    ];
    const existingLinks = selectors
      .map(selector =>
        Array.from(
          document.head.querySelectorAll<HTMLLinkElement>(selector),
        ),
      )
      .flat();

    if (existingLinks.length > 0) {
      const previousHrefs = existingLinks.map(link => link.href);
      existingLinks.forEach(link => {
        // Override existing tags that Next injects from static favicon files
        link.href = href;
      });

      return () => {
        existingLinks.forEach((link, index) => {
          link.href = previousHrefs[index];
        });
      };
    }

    const link = document.createElement('link');
    link.rel = 'icon';
    link.href = href;
    link.type = 'image/png';
    link.sizes = '32x32';

    document.head.appendChild(link);

    return () => {
      if (document.head.contains(link)) {
        document.head.removeChild(link);
      }
    };
  }, [faviconUrl]);
  

  return null;
};

export default RuntimeConfigInitializer;
