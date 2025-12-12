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
    const href = faviconUrl || '/favicon.ico';
    const head = document?.head;
    if (!head) {
      return;
    }
    const selector = "link[rel='icon']";
    let link = head.querySelector<HTMLLinkElement>(selector);
    if (!link) {
      link = document.createElement('link');
      link.rel = 'icon';
      head.appendChild(link);
    }
    link.href = href;
  }, [faviconUrl]);

  return null;
};

export default RuntimeConfigInitializer;
